import React, { ChangeEvent } from 'react';
import { QueryEditorProps } from '@grafana/data';
import { InlineField, Input, Stack } from '@grafana/ui';
import defaults from 'lodash/defaults';
import { DataSource } from './DataSource';
import { defaultQuery, OpenRVDASDataSourceOptions, OpenRVDASQuery } from './types';

type Props = QueryEditorProps<DataSource, OpenRVDASQuery, OpenRVDASDataSourceOptions>;
 
export function QueryEditor(props: Props) {
  const { onChange } = props;
  const query = defaults(props.query, defaultQuery);
  const { fields, seconds, backRecords, interval } = query;

  const onFieldsChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange({ ...query, fields: event.target.value });
  };

  const onSecondsChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange({ ...query, seconds: parseFloat(event.target.value) });
  };

  const onBackRecordsChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange({ ...query, backRecords: parseFloat(event.target.value) });
  };

  const onIntervalChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange({ ...query, interval: parseFloat(event.target.value) });
  };

  return (
    <Stack>
      <InlineField label="Comma separated fields" labelWidth={24} tooltip="Names of fields at the root level of the cache server">
        <Input data-testid="query-text" onChange={onFieldsChange} value={fields || ''} />
      </InlineField>
      <InlineField label="Seconds" labelWidth={12} tooltip="How many seconds to retrieve of historical data when first connecting to the cache server">
        <Input data-testid="seconds" onChange={onSecondsChange} value={seconds} type="number" step={1} />
      </InlineField>
      <InlineField label="Back Records" labelWidth={18} tooltip="How many historical records to return from the first request (overrides 'seconds' value)">
        <Input data-testid="backRecords" onChange={onBackRecordsChange} value={backRecords} type="number" step={1} />
      </InlineField>
      <InlineField label="Interval" labelWidth={13} tooltip="How long (in seconds) the server should wait between responses. Should be at least equal or less than the expected frequency of data updates to avoid missing data.">
        <Input data-testid="interval" onChange={onIntervalChange} value={interval} type="number" step={0.1} />
      </InlineField>
    </Stack>
  );
}
