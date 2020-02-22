/**
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

suite('fairness-metrics-table tests', () => {
  const TABLE_DATA = [
    {
      'slice': 'col:1',
      'metrics': {
        'loss': 0.7,
        'averageLabel': 0.5,
        'count': '1000000',
        'auprc': 0.7,
        'boundedAuc': {
          'value': 0.611111,
          'lowerBound': 0.6011111,
          'upperBound': 0.6211111
        },
      }
    },
    {
      'slice': 'col:2',
      'metrics': {
        'loss': 0.72,
        'averageLabel': 0.52,
        'count': '1000002',
        'auprc': 0.72,
        'boundedAuc':
            {'value': 0.612, 'lowerBound': 0.602, 'upperBound': 0.622},
      }
    },
    {
      'slice': 'col:3',
      'metrics': {
        'loss': 0.73,
        'count': '2000003',
        'auprc': 0.73,
        'boundedAuc':
            {'value': 0.613, 'lowerBound': 0.603, 'upperBound': 0.623},
      },
    }
  ];
  const TABLE_DATA_TO_COMPARE = [
    {
      'slice': 'col:1',
      'metrics': {
        'loss': 0.5,
        'averageLabel': 0.7,
        'count': '1000000',
        'auprc': 0.5,
        'boundedAuc': {
          'value': 0.411111,
          'lowerBound': 0.4011111,
          'upperBound': 0.4211111
        },
      }
    },
    {
      'slice': 'col:2',
      'metrics': {
        'loss': 0.52,
        'averageLabel': 0.72,
        'count': '1000002',
        'auprc': 0.52,
        'boundedAuc':
            {'value': 0.412, 'lowerBound': 0.402, 'upperBound': 0.422},
      }
    },
    {
      'slice': 'col:3',
      'metrics': {
        'loss': 0.53,
        'count': '2000003',
        'auprc': 0.53,
        'boundedAuc':
            {'value': 0.413, 'lowerBound': 0.403, 'upperBound': 0.423},
      },
    }
  ];

  const METRICS = ['loss', 'count', 'boundedAuc', 'auprc'];

  const EXAMPLE_COUNTS = [34, 84, 49];

  const MODEL_A_NAME = 'ModelA';
  const MODEL_B_NAME = 'ModelB';

  let table;

  test('ComputingTableData', done => {
    table = fixture('test-fixture');

    const fillData = () => {
      table.metrics = METRICS;
      table.data = TABLE_DATA;
      table.exampleCounts = EXAMPLE_COUNTS;
      table.evalName = MODEL_A_NAME;
      setTimeout(CheckProperties, 500);
    };

    const CheckProperties = () => {
      const expected_data = [
        ['feature', 'loss', 'count', 'boundedAuc', 'auprc'],
        ['col:1', '0.7', '1000000', '0.61111 (0.60111, 0.62111)', '0.7'],
        ['col:2', '0.72', '1000002', '0.61200 (0.60200, 0.62200)', '0.72'],
        ['col:3', '0.73', '2000003', '0.61300 (0.60300, 0.62300)', '0.73'],
      ];

      assert.equal(table.tableData_.length, expected_data.length);
      for (var i = 0; i < 4; i++) {
        for (var j = 0; j < 5; j++) {
          assert.equal(table.tableData_[i][j], expected_data[i][j]);
        }
      }

      table.shadowRoot.querySelectorAll('.table-row').forEach(function(row) {
        const cells = row.querySelectorAll('.table-entry');
        for (var i = 0; i < cells.length; i++) {
          const content = cells[i].textContent.trim();
          if (i % 2) {
            assert.isTrue(content[content.length - 1] === '%');
          } else {
            assert.isTrue(content[content.length - 1] != '%');
          }
        }
      });

      done();
    };

    setTimeout(fillData, 0);
  });

  test('ComputingTableData_ModelComparison', done => {
    table = fixture('test-fixture');

    const fillData = () => {
      table.metrics = METRICS;
      table.data = TABLE_DATA;
      table.dataCompare = TABLE_DATA_TO_COMPARE;
      table.exampleCounts = EXAMPLE_COUNTS;
      table.evalName = MODEL_A_NAME;
      table.evalNameCompare = MODEL_B_NAME;
      setTimeout(CheckProperties, 500);
    };

    const CheckProperties = () => {
      const expected_data = [
        [
          'feature', 'loss - ModelA', 'count - ModelA', 'boundedAuc - ModelA',
          'auprc - ModelA', 'loss - ModelB', 'count - ModelB',
          'boundedAuc - ModelB', 'auprc - ModelB'
        ],
        [
          'col:1', '0.7', '1000000', '0.61111 (0.60111, 0.62111)', '0.7', '0.5',
          '1000000', '0.41111 (0.40111, 0.42111)', '0.5'
        ],
        [
          'col:2', '0.72', '1000002', '0.61200 (0.60200, 0.62200)', '0.72',
          '0.52', '1000002', '0.41200 (0.40200, 0.42200)', '0.52'
        ],
        [
          'col:3', '0.73', '2000003', '0.61300 (0.60300, 0.62300)', '0.73',
          '0.53', '2000003', '0.41300 (0.40300, 0.42300)', '0.53'
        ],
      ];

      assert.equal(table.tableData_.length, expected_data.length);
      for (var i = 0; i < 4; i++) {
        for (var j = 0; j < 9; j++) {
          assert.equal(table.tableData_[i][j], expected_data[i][j]);
        }
      }

      table.shadowRoot.querySelectorAll('.table-row').forEach(function(row) {
        const cells = row.querySelectorAll('.table-entry');
        for (var i = 0; i < cells.length; i++) {
          const content = cells[i].textContent.trim();
          if (i % 2) {
            assert.isTrue(content[content.length - 1] === '%');
          } else {
            assert.isTrue(content[content.length - 1] != '%');
          }
        }
      });

      done();
    };

    setTimeout(fillData, 0);
  });
});
