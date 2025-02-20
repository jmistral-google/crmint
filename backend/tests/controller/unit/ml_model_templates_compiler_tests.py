# Copyright 2023 Google Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for controller.ml_model.templates.compiler."""

import re
from typing import Any, Union

from absl.testing import absltest
from freezegun import freeze_time

from common import utils
from controller import ml_model


class TestCompiler(absltest.TestCase):

  @freeze_time('2023-02-06T00:00:00')
  def test_build_training_pipeline(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    self.assertEqual(pipeline['name'], 'Test Model - Training')

    # schedule check
    self.assertEqual(pipeline['schedules'][0]['cron'], '0 0 6 2,5,8,11 *')

    # setup job check
    self.assertEqual(pipeline['jobs'][0]['name'], 'Test Model - Training Setup')
    params = pipeline['jobs'][0]['params']

    # big-query dataset location check
    dataset_loc_param = utils.first(
        params, lambda x: x['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # sql check start
    sql_param = utils.first(params, lambda x: x['name'] == 'script')
    self.assertIsNotNone(sql_param)

    # conversion value calculations job check
    self.assertEqual(
        pipeline['jobs'][1]['name'],
        'Test Model - Conversion Value Calculations')
    params = pipeline['jobs'][1]['params']

    # big-query dataset location check
    dataset_loc_param = utils.first(
        params, lambda x: x['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # sql check start
    sql_param = utils.first(params, lambda x: x['name'] == 'script')
    self.assertIsNotNone(sql_param)

  def test_build_model_sql_first_party_and_google_analytics(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    self.assertEqual(pipeline['name'], 'Test Model - Training')
    self.assertEqual(pipeline['jobs'][0]['name'], 'Test Model - Training Setup')
    params = pipeline['jobs'][0]['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # name check
    self.assertIn(
        'CREATE OR REPLACE MODEL `test-project-id-1234.test-dataset.model`',
        sql,
        'Model name check failed.')

    # event table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.events_*`',
        sql,
        'Event table name check failed.')

    # hyper-parameter check
    self.assertRegex(
        sql,
        r',[\s\n]+'.join([
            'HP1-NAME = "HP1-STRING"',
            'HP2-NAME = 1',
            'HP3-NAME = 13.7',
            'HP4-NAME = TRUE',
            'HP5-NAME = FALSE'
        ]),
        'Hyper-Parameter check failed.')

    # label check
    self.assertRegex(
        sql,
        r'[\s\n]+'.join([
            'WHERE name = "purchase"',
            'AND params.key = "value"',
            re.escape(
                'AND COALESCE(params.value.int_value,'
                ' params.value.float_value, params.value.double_value,'
                ' 0) > 0'
            ),
        ]),
        'Google Analytics label pull check failed.',
    )

    self.assertRegex(
        sql,
        re.escape('IFNULL(av.label, 0) AS label'),
        'Google Analytics label join check failed.',
    )

    # feature check
    self.assertRegex(
        sql,
        re.escape('SUM(IF(e.name = "click", 1, 0)) AS cnt_click'),
        'Google Analytics feature check failed.',
    )

    self.assertRegex(
        sql, re.escape('fp.subscribe'), 'First party feature check failed.'
    )

    # class-imbalance check
    self.assertIn(
        'MOD(ABS(FARM_FINGERPRINT(user_pseudo_id)), 100) > ((1 / 4) * 100)',
        sql,
        'Class-Imbalance check failed.',
    )

    # timespan check
    self.assertIn(
        'FORMAT_DATE("%Y%m%d", DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH))',
        sql,
        'Timespan start check failed.',
    )

    self.assertIn(
        'FORMAT_DATE("%Y%m%d", DATE_SUB(DATE_SUB(CURRENT_DATE(), INTERVAL 1'
        ' MONTH), INTERVAL 1 DAY))',
        sql,
        'Timespan end check failed.',
    )

  def test_build_model_sql_first_party(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        label={
            'name': 'enroll',
            'source': 'FIRST_PARTY',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'call', 'source': 'FIRST_PARTY'},
            {'name': 'request_for_info', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=1)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    params = pipeline['jobs'][0]['params']

    sql_param = utils.first(params, lambda x: x['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # label check
    self.assertRegex(
        sql,
        re.escape('fp.enroll'),
        'First party label check failed.')

    # feature check
    self.assertRegex(
        sql,
        r',[\s\n]+'.join([
            re.escape('fp.call'),
            re.escape('fp.request_for_info'),
        ]),
        'First party feature check failed.',
    )

    # class-imbalance check
    self.assertNotIn(
        'MOD(ABS(FARM_FINGERPRINT(user_pseudo_id)), 100) > ((1 / 4) * 100)',
        sql,
        'Class-Imbalance check failed. Should not exist when class imbalance is'
        ' set to 1.',
    )

  def test_build_model_sql_google_analytics(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=False,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'GOOGLE_ANALYTICS'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    params = pipeline['jobs'][0]['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # label check
    self.assertRegex(
        sql,
        r'[\s\n]+'.join([
            'WHERE name = "purchase"',
            'AND params.key = "value"',
            re.escape(
                'AND COALESCE(params.value.int_value,'
                ' params.value.float_value, params.value.double_value,'
                ' 0) > 0'
            ),
        ]),
        'Google Analytics label pull check failed.',
    )

    self.assertRegex(
        sql,
        re.escape('SELECT * FROM analytics_variables'),
        'Google Analytics label join check failed.',
    )

    # feature check
    self.assertRegex(
        sql,
        r',[\s\n]+'.join([
            re.escape('SUM(IF(e.name = "click", 1, 0)) AS cnt_click'),
            re.escape('SUM(IF(e.name = "subscribe", 1, 0)) AS cnt_subscribe'),
        ]),
        'Google Analytics feature check failed.')

  def test_build_model_sql_google_analytics_regression_model(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_REGRESSOR',
        uses_first_party_data=False,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'int'
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'GOOGLE_ANALYTICS'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    params = pipeline['jobs'][0]['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # first value join check
    self.assertRegex(
        sql,
        r'[\s\S]*'.join([
            re.escape('analytics_variables AS ('),
            re.escape('LEFT OUTER JOIN ('),
            re.escape('COALESCE(params.value.int_value, params.value.float_value, params.value.double_value, 0) AS value'),
            re.escape(') fv')
        ]),
        'Google Analytics first value join check failed.')

    # proper label and total value assignment check
    self.assertIn(
        '(label - first_value) AS label',
        sql,
        'Output label check failed.')

  def test_build_model_sql_google_analytics_classification_model(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=False,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'GOOGLE_ANALYTICS'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_training_pipeline(
        test_model, 'test-project-id-1234', 'test-ga4-dataset-loc')
    params = pipeline['jobs'][0]['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # random 90% selection check
    self.assertIn(
        'AND MOD(ABS(FARM_FINGERPRINT(user_pseudo_id)), 100) < 90',
        sql,
        'Google Analytics random 90% selection check failed.')

  @freeze_time('2023-02-06T00:00:00')
  def test_build_predictive_pipeline(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'string,int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    setup_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Setup')
    self.assertIsNotNone(setup_job)
    params = setup_job['params']

    # big-query dataset location check
    dataset_loc_param = next(
        param for param in params if param['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # schedule check
    self.assertEqual(pipeline['schedules'][0]['cron'], '0 0 * * *')

    # sql check start
    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)

    output_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Output')
    self.assertIsNotNone(output_job)

    # check job start conditions
    self.assertEqual(
        output_job['hash_start_conditions'][0]['preceding_job_id'],
        setup_job['id'])

    params = output_job['params']

    # big-query dataset location check
    dataset_loc_param = next(
        param for param in params if param['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # sql check start
    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)

    ga4_upload_job = next(
        job for job in pipeline['jobs'] if job['name'] == 'Test Model - Predictive GA4 Upload')
    self.assertIsNotNone(ga4_upload_job)

    # check job start conditions
    self.assertEqual(
        ga4_upload_job['hash_start_conditions'][0]['preceding_job_id'], output_job['id'])

    params = ga4_upload_job['params']

    # project id check
    bq_project_id_param = next(
        param for param in params if param['name'] == 'bq_project_id')
    self.assertIsNotNone(bq_project_id_param)
    self.assertEqual(bq_project_id_param['value'], 'test-project-id-1234')

    # big-query dataset name check
    dataset_name_param = next(
        param for param in params if param['name'] == 'bq_dataset_id')
    self.assertIsNotNone(dataset_name_param)
    self.assertEqual(dataset_name_param['value'], 'test-dataset')

    # big-query dataset location check
    dataset_loc_param = next(
        param for param in params if param['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # measurement id check
    measurement_id_param = next(
        param for param in params if param['name'] == 'measurement_id')
    self.assertIsNotNone(measurement_id_param)
    self.assertEqual(measurement_id_param['value'], 'test-ga4-measurement-id')

    # api secret check
    api_secret_param = next(
        param for param in params if param['name'] == 'api_secret')
    self.assertIsNotNone(api_secret_param)
    self.assertEqual(api_secret_param['value'], 'test-ga4-api-secret')

    # template check
    template_param = next(
        param for param in params if param['name'] == 'template')
    self.assertIsNotNone(template_param)

  def test_build_predictive_sql_first_party_and_google_analytics(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'string,int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    setup_job = next(
        job for job in pipeline['jobs'] if job['name'] == 'Test Model - Predictive Setup')
    self.assertIsNotNone(setup_job)
    params = setup_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # name check
    self.assertIn(
        'CREATE OR REPLACE TABLE `test-project-id-1234.test-dataset.predictions`',
        sql,
        'Predictions table name check failed.')

    # training table check
    self.assertIn(
        'FROM ML.PREDICT(MODEL `test-project-id-1234.test-dataset.model`',
        sql,
        'Not able to find training model dataset callout.')

    # event table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.events_*`',
        sql,
        'Event table name check failed.')

    # label check
    self.assertRegex(
        sql,
        r'[\s\n]+'.join([
            'WHERE name = "purchase"',
            'AND params.key = "value"',
            re.escape('AND COALESCE(params.value.string_value, params.value.int_value) NOT IN ("", "0", 0, NULL)')
        ]),
        'Google Analytics label pull check failed.')

    self.assertRegex(
        sql,
        re.escape('IFNULL(av.label, 0) AS label'),
        'Google Analytics label join check failed.')

    # feature check
    self.assertRegex(
        sql,
        re.escape('SUM(IF(e.name = "click", 1, 0)) AS cnt_click'),
        'Google Analytics feature check failed.')

    self.assertRegex(
        sql,
        re.escape('fp.subscribe'),
        'First party feature check failed.')

    # timespan check
    self.assertIn(
        'FORMAT_DATE("%Y%m%d", DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH))',
        sql,
        'Timespan start check failed.')

    self.assertIn(
        'FORMAT_DATE("%Y%m%d", DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY))',
        sql,
        'Timespan end check failed.')

  def test_build_predictive_sql_first_party(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        unique_id='USER_ID',
        label={
            'name': 'premium_subscription',
            'source': 'FIRST_PARTY',
            'key': 'value',
            'value_type': 'int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'purchase', 'source': 'FIRST_PARTY'},
            {'name': 'request_for_info', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    setup_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Setup')
    self.assertIsNotNone(setup_job)
    params = setup_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # Probability check
    self.assertIn(
        'plp.prob AS probability,',
        sql,
        'Probability not found in select when selecting from ML.PREDICT.')

    # user ids check
    self.assertRegex(
        sql,
        r'[\s\S]+'.join([
            'SELECT',
            'user_id,',
            'user_pseudo_id,',
            re.escape('ML.PREDICT')
        ]),
        'User ids check failed.')

    # label check
    self.assertIn(
        'fp.premium_subscription AS label,',
        sql,
        'First party label check failed.')

    # feature check
    self.assertRegex(
        sql,
        r',[\s\n]+'.join([
            re.escape('fp.purchase'),
            re.escape('fp.request_for_info'),
        ]),
        'First party feature check failed.')

  def test_build_predictive_sql_google_analytics(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=False,
        label={
            'name': 'subscription',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'string',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'scroll', 'source': 'GOOGLE_ANALYTICS'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    setup_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Setup')
    self.assertIsNotNone(setup_job)
    params = setup_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # label check
    self.assertRegex(
        sql,
        r'[\s\n]+'.join([
            'WHERE name = "subscription"',
            'AND params.key = "value"',
            re.escape('AND COALESCE(params.value.string_value, params.value.int_value) NOT IN ("", "0", 0, NULL)')
        ]),
        'Google Analytics label pull check failed.')

    self.assertRegex(
        sql,
        re.escape('SELECT * FROM analytics_variables'),
        'Google Analytics label join check failed.')

    # feature check
    self.assertRegex(
        sql,
        r',[\s\n]+'.join([
            re.escape('SUM(IF(e.name = "click", 1, 0)) AS cnt_click'),
            re.escape('SUM(IF(e.name = "scroll", 1, 0)) AS cnt_scroll')
        ]),
        'Google Analytics feature check failed.')

  def test_build_predictive_sql_google_analytics_regression_model(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_REGRESSOR',
        uses_first_party_data=False,
        label={
            'name': 'subscription',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'string'
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'scroll', 'source': 'GOOGLE_ANALYTICS'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    setup_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Setup')
    self.assertIsNotNone(setup_job)
    params = setup_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # first value join check
    self.assertRegex(
        sql,
        r'[\s\S]*'.join([
            re.escape('analytics_variables AS ('),
            re.escape('LEFT OUTER JOIN ('),
            re.escape(
                'COALESCE(params.value.int_value, params.value.float_value,'
                ' params.value.double_value, 0) AS value'
            ),
            re.escape(') fv'),
        ]),
        'Google Analytics first value join check failed.',
    )

    # proper label and total value assignment check
    self.assertRegex(
        sql,
        r'[\s\S]*'.join([
            re.escape('label AS total_value,'),
            re.escape('(label - first_value) AS label'),
        ]),
        'Output label and total_value check failed.',
    )

  def test_build_output_sql_classification_model(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        unique_id='USER_ID',
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'string,int',
            'average_value': 1234.0
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    output_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Output')
    self.assertIsNotNone(output_job)
    params = output_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # name check
    self.assertIn(
        'CREATE OR REPLACE TABLE `test-project-id-1234.test-dataset.output`',
        sql,
        'Scores table name check failed.',
    )

    # predictions table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-dataset.predictions`',
        sql,
        'Predictions table name check failed.',
    )

    # events table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.events_*`',
        sql,
        'Events table name check failed.',
    )

    # summary table check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.__TABLES_SUMMARY__`',
        sql,
        'Summary table name check failed.',
    )

    # conversion values join check
    self.assertIn(
        'LEFT OUTER JOIN'
        ' `test-project-id-1234.test-dataset.conversion_values` cv',
        sql,
        'Failed conversion values join check.',
    )

    # user id check
    self.assertIn(
        'p.user_id,',
        sql,
        'Failed user id check within prediction preparation step.',
    )

    # score check
    self.assertIn(
        'MAX(p.probability) * 100 AS score',
        sql,
        'Failed score check within prediction preparation step.',
    )

  def test_build_output_sql_regression_model(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_REGRESSOR',
        uses_first_party_data=True,
        unique_id='USER_ID',
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'float'
        },
        features=[
            {'name': 'click', 'source': 'GOOGLE_ANALYTICS'},
            {'name': 'subscribe', 'source': 'FIRST_PARTY'}
        ],
        class_imbalance=4)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    output_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive Output')
    self.assertIsNotNone(output_job)
    params = output_job['params']

    sql_param = next(param for param in params if param['name'] == 'script')
    self.assertIsNotNone(sql_param)
    sql = sql_param['value']

    # name check
    self.assertIn(
        'CREATE OR REPLACE TABLE `test-project-id-1234.test-dataset.output`',
        sql,
        'Scores table name check failed.')

    # predictions table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-dataset.predictions`',
        sql,
        'Predictions table name check failed.')

    # events table name check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.events_*`',
        sql,
        'Events table name check failed.')

    # summary table check
    self.assertIn(
        'FROM `test-project-id-1234.test-ga4-dataset-loc.__TABLES_SUMMARY__`',
        sql,
        'Summary table name check failed.')

    # revenue check
    self.assertIn(
        'IF(predicted_label > 0, ROUND(predicted_label, 4), 0) AS revenue',
        sql,
        'Failed label revenue check within prediction preparation step.')

    # user id check
    self.assertIn(
        'user_id,',
        sql,
        'Failed user id check within prediction preparation step.')

  def test_build_ga4_request(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_REGRESSOR',
        uses_first_party_data=False,
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'float'
        },
        features=[],
        class_imbalance=0)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    upload_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive GA4 Upload')
    self.assertIsNotNone(upload_job)
    params = upload_job['params']

    # big-query dataset id check
    dataset_id_param = utils.first(
        params, lambda param: param['name'] == 'bq_dataset_id')
    self.assertIsNotNone(dataset_id_param)
    self.assertEqual(dataset_id_param['value'], 'test-dataset')

    # big-query dataset location check
    dataset_loc_param = utils.first(
        params, lambda param: param['name'] == 'bq_dataset_location')
    self.assertIsNotNone(dataset_loc_param)
    self.assertEqual(dataset_loc_param['value'], 'US')

    # ga4 measurement id check
    measurement_id_param = utils.first(
        params, lambda param: param['name'] == 'measurement_id')
    self.assertIsNotNone(measurement_id_param)
    self.assertEqual(measurement_id_param['value'], 'test-ga4-measurement-id')

    # ga4 api secret check
    api_secret_param = utils.first(
        params, lambda param: param['name'] == 'api_secret')
    self.assertIsNotNone(api_secret_param)
    self.assertEqual(api_secret_param['value'], 'test-ga4-api-secret')

  def test_build_ga4_request_score(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_CLASSIFIER',
        uses_first_party_data=True,
        unique_id='USER_ID',
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'float',
            'average_value': 1234.0
        },
        features=[],
        class_imbalance=0)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    upload_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive GA4 Upload')
    self.assertIsNotNone(upload_job)
    params = upload_job['params']

    # template check
    template_param = utils.first(
        params, lambda param: param['name'] == 'template')
    self.assertIsNotNone(template_param)

    self.assertJsonEqual(
        template_param['value'],
        r"""
          {
            "clientId": "${client_id}",
            "userId": "${user_id}",
            "nonPersonalizedAds": false,
            "events": [
              {
                "name": "${event_name}",
                "params": {
                  "type": "${type}",
                  "value": "${value}",
                  "score": "${score}",
                  "nscore": "${normalized_score}"
                }
              }
            ]
          }
        """,
        'Failed template check.')

  def test_build_ga4_request_revenue(self):
    test_model = self.model_config(
        field_type='BOOSTED_TREE_REGRESSOR',
        uses_first_party_data=True,
        unique_id='USER_ID',
        label={
            'name': 'purchase',
            'source': 'GOOGLE_ANALYTICS',
            'key': 'value',
            'value_type': 'float'
        },
        features=[],
        class_imbalance=0)

    pipeline = ml_model.compiler.build_predictive_pipeline(
        test_model,
        'test-project-id-1234',
        'test-ga4-dataset-loc',
        'test-ga4-measurement-id',
        'test-ga4-api-secret')
    self.assertEqual(pipeline['name'], 'Test Model - Predictive')

    upload_job = utils.first(
        pipeline['jobs'],
        lambda job: job['name'] == 'Test Model - Predictive GA4 Upload')
    self.assertIsNotNone(upload_job)
    params = upload_job['params']

    # template check
    template_param = utils.first(
        params, lambda param: param['name'] == 'template')
    self.assertIsNotNone(template_param)

    self.assertJsonEqual(
        template_param['value'],
        r"""
          {
            "clientId": "${client_id}",
            "userId": "${user_id}",
            "nonPersonalizedAds": false,
            "events": [
              {
                "name": "${event_name}",
                "params": {
                  "type": "${type}",
                  "value": "${value}",
                  "revenue": "${revenue}"
                }
              }
            ]
          }
        """,
        'Failed template check.')

  def model_config(self,
                   field_type: str,
                   uses_first_party_data: bool,
                   label: dict[str, Any],
                   features: list[dict[str, Any]],
                   class_imbalance: int,
                   unique_id: str = 'CLIENT_ID'):
    return self.convert_to_object({
        'name': 'Test Model',
        'bigquery_dataset': {
            'location': 'US',
            'name': 'test-dataset'
        },
        'type': field_type,
        'uses_first_party_data': uses_first_party_data,
        'unique_id': unique_id,
        'hyper_parameters': [
            {'name': 'HP1-NAME', 'value': 'HP1-STRING'},
            {'name': 'HP2-NAME', 'value': '1'},
            {'name': 'HP3-NAME', 'value': '13.7'},
            {'name': 'HP4-NAME', 'value': 'true'},
            {'name': 'HP5-NAME', 'value': 'false'}
        ],
        'label': label,
        'features': features,
        'class_imbalance': class_imbalance,
        'timespans': [
            {'name': 'training', 'value': 17, 'unit': 'month'},
            {'name': 'predictive', 'value': 1, 'unit': 'month'}
        ]
    })

  def convert_to_object(self, collection: Union[dict[str, Any], list[Any]]):
    class TempObject:
      pass

    if isinstance(collection, list):
      for key, value in enumerate(collection):
        collection[key] = self.convert_to_object(value)
    elif isinstance(collection, dict):
      temp = TempObject()
      for key, value in collection.items():
        temp.__dict__[key] = self.convert_to_object(value)
      return temp

    return collection


if __name__ == '__main__':
  absltest.main()
