# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Predict extractor for TFLite models."""

import collections
import copy
from typing import Dict, Sequence, Union

from absl import logging
import apache_beam as beam
import numpy as np
import tensorflow as tf
from tensorflow_model_analysis import constants
from tensorflow_model_analysis import types
from tensorflow_model_analysis.extractors import extractor
from tensorflow_model_analysis.proto import config_pb2
from tensorflow_model_analysis.utils import model_util

_TFLITE_PREDICT_EXTRACTOR_STAGE_NAME = 'ExtractTFLitePredictions'


# TODO(b/149981535) Determine if we should merge with RunInference.
@beam.typehints.with_input_types(types.Extracts)
@beam.typehints.with_output_types(types.Extracts)
class _TFLitePredictionDoFn(model_util.BatchReducibleBatchedDoFnWithModels):
  """A DoFn that loads tflite models and predicts."""

  def __init__(self, eval_config: config_pb2.EvalConfig,
               eval_shared_models: Dict[str, types.EvalSharedModel]) -> None:
    super().__init__({k: v.model_loader for k, v in eval_shared_models.items()})
    self._eval_config = eval_config

  def setup(self):
    super().setup()
    self._interpreters = {}
    for model_name, model_contents in self._loaded_models.items():
      self._interpreters[model_name] = tf.lite.Interpreter(
          model_content=model_contents.contents)

  def _get_input_name_from_input_detail(self, input_detail):
    """Get input name from input detail.

    Args:
      input_detail: the details for a model input.

    Returns:
      Input name. The signature key prefix and argument postfix will be removed.
    """
    input_name = input_detail['name']
    # TFLite saved model converter inserts the signature key name at beginning
    # of the input names. TFLite rewriter assumes that the default signature key
    # ('serving_default') will be used as an exported name when saving.
    if input_name.startswith('serving_default_'):
      input_name = input_name[len('serving_default_'):]
    return input_name.split(':')[0]

  def _batch_reducible_process(
      self, element: types.Extracts) -> Sequence[types.Extracts]:
    """Invokes the tflite model on the provided inputs and stores the result."""
    result = copy.copy(element)
    result[constants.PREDICTIONS_KEY] = []
    feature_rows = element[constants.FEATURES_KEY]

    for spec in self._eval_config.model_specs:
      model_name = spec.name if len(self._eval_config.model_specs) > 1 else ''
      if model_name not in self._loaded_models:
        raise ValueError(
            f'model for "{spec.name}" not found: eval_config={self._eval_config}'
        )

      interpreter = self._interpreters[model_name]

      input_details = interpreter.get_input_details()
      output_details = interpreter.get_output_details()

      input_features = collections.defaultdict(list)
      for i in input_details:
        input_name = self._get_input_name_from_input_detail(i)
        # The batch dimension is the specific batch size of the last time the
        # model was invoked. Set it to 1 to "reset".
        input_shape = [1] + list(i['shape'])[1:]
        input_type = i['dtype']
        for r in feature_rows:
          value = r.get(input_name)
          if value is None or np.any(np.equal(value, None)):
            default = -1 if input_type in [np.float32, np.int64] else ''
            value = np.empty(input_shape)
            value.fill(default)
            value = value.astype(input_type)
            logging.log_every_n(logging.WARNING,
                                'Feature %s not found. Setting default value.',
                                100, input_name)
          else:
            value = np.reshape(value, input_shape)
          input_features[input_name].append(value)
        input_features[input_name] = tf.concat(
            input_features[input_name], axis=0)
        if np.shape(input_features[input_name]) != tuple(i['shape']):
          interpreter.resize_tensor_input(i['index'],
                                          np.shape(input_features[input_name]))
      interpreter.allocate_tensors()

      for i in input_details:
        input_name = self._get_input_name_from_input_detail(i)
        interpreter.set_tensor(i['index'], input_features[input_name])
      interpreter.invoke()

      outputs = {
          o['name']: interpreter.get_tensor(o['index']) for o in output_details
      }

      for v in outputs.values():
        if len(v) != len(feature_rows):
          raise ValueError('Did not get the expected number of results.')

      for i in range(len(feature_rows)):
        output = {k: v[i] for k, v in outputs.items()}

        if len(output) == 1:
          output = list(output.values())[0]

        if len(self._eval_config.model_specs) == 1:
          result[constants.PREDICTIONS_KEY].append(output)
        else:
          if i >= len(result[constants.PREDICTIONS_KEY]):
            result[constants.PREDICTIONS_KEY].append({})
          result[constants.PREDICTIONS_KEY][i].update({spec.name: output})
    return [result]


@beam.ptransform_fn
@beam.typehints.with_input_types(types.Extracts)
@beam.typehints.with_output_types(types.Extracts)
def _ExtractTFLitePredictions(  # pylint: disable=invalid-name
    extracts: beam.pvalue.PCollection, eval_config: config_pb2.EvalConfig,
    eval_shared_models: Dict[str,
                             types.EvalSharedModel]) -> beam.pvalue.PCollection:
  """A PTransform that adds predictions and possibly other tensors to extracts.

  Args:
    extracts: PCollection of extracts containing model inputs keyed by
      tfma.FEATURES_KEY.
    eval_config: Eval config.
    eval_shared_models: Shared model parameters keyed by model name.

  Returns:
    PCollection of Extracts updated with the predictions.
  """
  return (
      extracts
      | 'Predict' >> beam.ParDo(
          _TFLitePredictionDoFn(
              eval_config=eval_config, eval_shared_models=eval_shared_models)))


def TFLitePredictExtractor(
    eval_config: config_pb2.EvalConfig,
    eval_shared_model: Union[types.EvalSharedModel, Dict[str,
                                                         types.EvalSharedModel]]
) -> extractor.Extractor:
  """Creates an extractor for performing predictions on tflite models.

  The extractor's PTransform loads and interprets the tflite flatbuffer against
  every extract yielding a copy of the incoming extracts with an additional
  extract added for the predictions keyed by tfma.PREDICTIONS_KEY. The model
  inputs are searched for under tfma.FEATURES_KEY. If multiple
  models are used the predictions will be stored in a dict keyed by model name.

  Args:
    eval_config: Eval config.
    eval_shared_model: Shared model (single-model evaluation) or dict of shared
      models keyed by model name (multi-model evaluation).

  Returns:
    Extractor for extracting predictions.
  """
  eval_shared_models = model_util.verify_and_update_eval_shared_models(
      eval_shared_model)

  # pylint: disable=no-value-for-parameter
  return extractor.Extractor(
      stage_name=_TFLITE_PREDICT_EXTRACTOR_STAGE_NAME,
      ptransform=_ExtractTFLitePredictions(
          eval_config=eval_config,
          eval_shared_models={m.model_name: m for m in eval_shared_models}))
