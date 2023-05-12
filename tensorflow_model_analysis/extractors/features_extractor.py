# Copyright 2020 Google LLC
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
"""Features extractor."""

import copy
from typing import Optional, Tuple

import apache_beam as beam
import numpy as np
import pyarrow as pa
from tensorflow_model_analysis import constants
from tensorflow_model_analysis import types
from tensorflow_model_analysis.extractors import extractor
from tensorflow_model_analysis.proto import config_pb2

_FEATURES_EXTRACTOR_STAGE_NAME = 'ExtractFeatures'


def FeaturesExtractor(
    eval_config: config_pb2.EvalConfig) -> extractor.Extractor:
  """Creates an extractor for extracting features.

  The extractor's PTransform extracts features from an Arrow RecordBatch stored
  under tfma.ARROW_RECORD_BATCH_KEY in the incoming extract and adds them to the
  output extract under the key tfma.FEATURES_KEY. Any extracts that already
  exist will be merged with the values parsed by this extractor with this
  extractor's values taking precedence when duplicate keys are detected.

  Args:
    eval_config: Eval config.

  Returns:
    Extractor for extracting features.
  """
  del eval_config
  # pylint: disable=no-value-for-parameter
  return extractor.Extractor(
      stage_name=_FEATURES_EXTRACTOR_STAGE_NAME, ptransform=_ExtractFeatures())


def _IsListLike(arrow_type: pa.DataType) -> bool:
  return pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type)


def _IsBinaryLike(arrow_type: pa.DataType) -> bool:
  return (pa.types.is_binary(arrow_type) or
          pa.types.is_large_binary(arrow_type) or
          pa.types.is_string(arrow_type) or
          pa.types.is_large_string(arrow_type))


def _IsSupportedArrowValueType(arrow_type: pa.DataType) -> bool:
  return (pa.types.is_integer(arrow_type) or pa.types.is_floating(arrow_type) or
          _IsBinaryLike(arrow_type))


def _DropUnsupportedColumnsAndFetchRawDataColumn(
    record_batch: pa.RecordBatch
) -> Tuple[pa.RecordBatch, Optional[np.ndarray]]:
  """Drops unsupported columns and fetches the raw data column.

  Currently, types that are not binary_like or ListArray[primitive types] are
  dropped.

  Args:
    record_batch: An Arrow RecordBatch.

  Returns:
    Arrow RecordBatch with only supported columns.
  """
  column_names, column_arrays = [], []
  serialized_examples = None
  for column_name, column_array in zip(record_batch.schema.names,
                                       record_batch.columns):
    column_type = column_array.type
    if column_name == constants.ARROW_INPUT_COLUMN:
      assert _IsListLike(column_type) and _IsBinaryLike(
          column_type.value_type
      ), f'Invalid type for batched input key: {column_type}. Expected binary like.'
      serialized_examples = np.asarray(column_array.flatten())
    elif (_IsListLike(column_type) and
          _IsSupportedArrowValueType(column_type.value_type)):
      column_names.append(column_name)
      column_arrays.append(column_array)
  return (pa.RecordBatch.from_arrays(column_arrays,
                                     column_names), serialized_examples)


@beam.ptransform_fn
@beam.typehints.with_input_types(types.Extracts)
@beam.typehints.with_output_types(types.Extracts)
def _ExtractFeatures(
    extracts: beam.pvalue.PCollection) -> beam.pvalue.PCollection:
  """Extracts features from extracts.

  Args:
    extracts: PCollection containing features under tfma.FEATURES_KEY.

  Returns:
    PCollection of extracts with additional features added under the key
    tfma.FEATURES_KEY.
  """

  def extract_features(  # pylint: disable=invalid-name
        batched_extract: types.Extracts) -> types.Extracts:
    """Extract features from extracts containing arrow table."""
    result = copy.copy(batched_extract)
    (record_batch, serialized_examples) = (
        _DropUnsupportedColumnsAndFetchRawDataColumn(
            batched_extract[constants.ARROW_RECORD_BATCH_KEY]))
    # Special case: if record_batch contains 0 column, it will have 0 row, but
    # we want a list of empty dicts, of the same length as serialized_examples.
    if record_batch.num_columns == 0:
      result[constants.FEATURES_KEY] = [{} for _ in serialized_examples]
    else:
      dataframe = record_batch.to_pandas()
      result[constants.FEATURES_KEY] = dataframe.to_dict(orient='records')
    # TODO(pachristopher): Consider avoiding setting this key if we don't need
    # this any further in the pipeline. This can avoid a potentially costly copy
    result[constants.INPUT_KEY] = serialized_examples
    return result

  return extracts | 'ExtractFeatures' >> beam.Map(extract_features)
