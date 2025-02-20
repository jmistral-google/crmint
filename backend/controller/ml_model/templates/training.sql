CREATE OR REPLACE MODEL `{{project_id}}.{{model_dataset}}.model`
OPTIONS (
  MODEL_TYPE = "{{type.name}}",
  -- inject the selected hyper parameters
  {% for param in hyper_parameters %}
  {% if is_number(param.value) %}
  {{param.name}} = {{param.value}},
  {% elif is_bool(param.value) %}
  {{param.name}} = {{param.value.upper()}},
  {% else %}
  {{param.name}} = "{{param.value}}",
  {% endif %}
  {% endfor %}
  INPUT_LABEL_COLS = ["label"]
) AS
WITH events AS (
  SELECT
    event_timestamp AS timestamp,
    event_date AS date,
    event_name AS name,
    event_params AS params,
    {{unique_id}},
    geo.country AS country,
    geo.region AS region,
    device.language AS language,
    device.category AS device_type,
    device.operating_system AS device_os,
    device.web_info.browser AS device_browser,
    traffic_source.source AS traffic_source,
    traffic_source.medium AS traffic_medium,
    EXTRACT(HOUR FROM(TIMESTAMP_MICROS(user_first_touch_timestamp))) AS first_touch_hour
  FROM `{{project_id}}.{{ga4_dataset}}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN
    FORMAT_DATE("%Y%m%d", DATE_SUB(CURRENT_DATE(), INTERVAL {{timespan.training_start}} MONTH)) AND
    FORMAT_DATE("%Y%m%d", DATE_SUB(DATE_SUB(CURRENT_DATE(), INTERVAL {{timespan.predictive_start}} MONTH), INTERVAL 1 DAY))
  {% if type.is_classification %}
  -- get 90% of the events in this time-range (the other 10% is used to calculate conversion values)
  AND MOD(ABS(FARM_FINGERPRINT({{unique_id}})), 100) < 90
  {% endif %}
),
-- pull together a list of first engagements and associated metadata that will be useful for the model
first_engagement AS (
  SELECT * EXCEPT(row_num)
  FROM (
    SELECT
      {{unique_id}},
      country,
      region,
      language,
      traffic_source,
      traffic_medium,
      device_type,
      device_os,
      device_browser,
      CASE
        WHEN first_touch_hour >= 1 AND first_touch_hour < 6 THEN "night_1_6"
        WHEN first_touch_hour >= 6 AND first_touch_hour < 11 THEN "morning_6_11"
        WHEN first_touch_hour >= 11 AND first_touch_hour < 14 THEN "lunch_11_14"
        WHEN first_touch_hour >= 14 AND first_touch_hour < 17 THEN "afternoon_14_17"
        WHEN first_touch_hour >= 17 AND first_touch_hour < 19 THEN "dinner_17_19"
        WHEN first_touch_hour >= 19 AND first_touch_hour < 22 THEN "evening_19_23"
        WHEN first_touch_hour >= 22 OR first_touch_hour = 0 THEN "latenight_23_1"
      END AS daypart,
      ROW_NUMBER() OVER (PARTITION BY {{unique_id}} ORDER BY timestamp ASC) AS row_num
    FROM events
    WHERE name = "user_engagement"
  )
  WHERE row_num = 1
),
-- if the selected label is a google analytics event then pull these per user
{% if label.source == 'GOOGLE_ANALYTICS' %}
analytics_variables AS (
  SELECT
    fe.{{unique_id}},
    {% if type.is_regression %}
    IFNULL(fv.value, 0) AS first_value,
    {% endif %}
    IFNULL(l.label, 0) AS label,
    l.date AS trigger_event_date
  FROM first_engagement fe
  LEFT OUTER JOIN (
    SELECT
      e.{{unique_id}},
      {% if type.is_classification %}
      1 AS label,
      {% elif type.is_regression %}
      SUM(COALESCE(params.value.int_value, params.value.float_value, params.value.double_value, 0)) AS label,
      {% endif %}
      MIN(e.date) AS date,
    FROM events AS e, UNNEST(params) AS params
    WHERE name = "{{label.name}}"
    AND params.key = "{{label.key}}"
    {% if 'string' in label.value_type %}
    AND COALESCE(params.value.string_value, params.value.int_value) NOT IN ("", "0", 0, NULL)
    {% else %}
    AND COALESCE(params.value.int_value, params.value.float_value, params.value.double_value, 0) > 0
    {% endif %}
    GROUP BY 1
  ) l
  ON fe.{{unique_id}} = l.{{unique_id}}
  -- add the first value in as a feature (first purchase/etc)
  {% if type.is_regression %}
  LEFT OUTER JOIN (
    SELECT
      e.{{unique_id}},
      COALESCE(params.value.int_value, params.value.float_value, params.value.double_value, 0) AS value,
      ROW_NUMBER() OVER (PARTITION BY e.{{unique_id}} ORDER BY e.timestamp ASC) AS row_num
    FROM events AS e, UNNEST(params) AS params
    WHERE name = "{{label.name}}"
    AND params.key = "{{label.key}}"
    AND COALESCE(params.value.int_value, params.value.float_value, params.value.double_value, 0) > 0
  ) fv
  ON fe.{{unique_id}} = fv.{{unique_id}}
  AND fv.row_num = 1
  {% endif %}
),
{% endif %}
{% if uses_first_party_data %}
user_variables AS (
  SELECT
    fp.{{unique_id}},
    -- inject the selected first party features
    {% for feature in features %}
    {% if feature.source == 'FIRST_PARTY' %}
    fp.{{feature.name}},
    {% endif %}
    {% endfor %}
    -- inject the selected first party label
    {% if label.source == 'FIRST_PARTY' %}
    fp.{{label.name}} AS label,
    fp.trigger_event_date
    -- or inject the selected google analytics label
    {% elif label.source == 'GOOGLE_ANALYTICS' %}
    IFNULL(av.label, 0) AS label,
    COALESCE(fp.trigger_event_date, av.trigger_event_date) AS trigger_event_date
    {% endif %}
  FROM `{{project_id}}.{{model_dataset}}.first_party` fp
  {% if label.source == 'GOOGLE_ANALYTICS' %}
  LEFT OUTER JOIN analytics_variables av
  ON fp.{{unique_id}} = av.{{unique_id}}
  {% endif %}
),
{% else %}
user_variables AS (
  SELECT * FROM analytics_variables
),
{% endif %}
user_aggregate_behavior AS (
  SELECT
    e.{{unique_id}},
    SUM((SELECT value.int_value FROM UNNEST(e.params) WHERE key = "engagement_time_msec")) AS engagement_time,
    SUM(IF(e.name = "user_engagement", 1, 0)) AS cnt_user_engagement,
    SUM(IF(e.name = "scroll", 1, 0)) AS cnt_scroll,
    SUM(IF(e.name = "session_start", 1, 0)) AS cnt_session_start,
    SUM(IF(e.name = "first_visit", 1, 0)) AS cnt_first_visit,
    -- inject the selected google analytics features
    {% for feature in features %}
    {% if feature.source == 'GOOGLE_ANALYTICS' %}
    SUM(IF(e.name = "{{feature.name}}", 1, 0)) AS cnt_{{feature.name}},
    {% endif %}
    {% endfor %}
    SUM(IF(e.name = "page_view", 1, 0)) AS cnt_page_view
  FROM events AS e
  INNER JOIN user_variables AS uv
  ON e.{{unique_id}} = uv.{{unique_id}}
  WHERE (uv.label > 0 AND e.date <= uv.trigger_event_date)
  OR uv.label = 0
  GROUP BY 1
),
training_dataset AS (
  SELECT
    fe.*,
    uab.* EXCEPT({{unique_id}}),
    uv.* EXCEPT({{unique_id}}, trigger_event_date)
  FROM first_engagement AS fe
  INNER JOIN user_aggregate_behavior AS uab
  ON fe.{{unique_id}} = uab.{{unique_id}}
  INNER JOIN user_variables AS uv
  ON fe.{{unique_id}} = uv.{{unique_id}}
)
{% if type.is_classification %}
SELECT * EXCEPT({{unique_id}})
{% elif type.is_regression %}
SELECT
  * EXCEPT({{unique_id}}, label),
  (label - first_value) AS label
{% endif %}
FROM training_dataset
{% if class_imbalance > 1 %}
WHERE label > 0
UNION ALL
SELECT * EXCEPT({{unique_id}})
FROM training_dataset
WHERE label = 0
AND MOD(ABS(FARM_FINGERPRINT({{unique_id}})), 100) > ((1 / {{class_imbalance}}) * 100)
{% endif %}
