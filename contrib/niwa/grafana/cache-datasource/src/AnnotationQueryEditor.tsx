import React, { ChangeEvent } from 'react';
import { AnnotationQuery, QueryEditorProps } from '@grafana/data';
import { InlineField, Input, Stack } from '@grafana/ui';
import defaults from 'lodash/defaults';
import { DataSource } from './DataSource';
import { defaultQuery, OpenRVDASDataSourceOptions, OpenRVDASQuery } from './types';

console.log("annotation load")

type Props = QueryEditorProps<DataSource, OpenRVDASQuery, OpenRVDASDataSourceOptions> & {
  annotation?: AnnotationQuery<OpenRVDASQuery>;
  onAnnotationChange?: (annotation: AnnotationQuery<OpenRVDASQuery>) => void;
};
  
export function AnnotationQueryEditor(props: Props) {
  // This is because of problematic typing. See AnnotationQueryEditorProps in grafana-data/annotations.ts.
  console.log("annotation render", props);
  const annotation = props.annotation!;
  const onAnnotationChange = props.onAnnotationChange!;

  const query = defaults(annotation, defaultQuery);
  const { fields, seconds } = query;
 
  const onFieldsChange = (event: ChangeEvent<HTMLInputElement>) => {
    console.log("annotation fields change", {...annotation, fields: event.target.value})
    onAnnotationChange({...annotation, fields: event.target.value});
  };

  const onSecondsChange = (event: ChangeEvent<HTMLInputElement>) => {
    console.log("annotation seconds change", {...annotation, seconds: parseFloat(event.target.value)})
    onAnnotationChange({...annotation, seconds: parseFloat(event.target.value)});
  };

  return (
    <Stack>
      <InlineField label="Comma separated fields" labelWidth={42} tooltip="Names of fields at the root level of the cache server, the first field will be used as the title">
        <Input data-testid="query-text" onChange={onFieldsChange} value={fields || ''} />
      </InlineField>
      <InlineField label="Seconds" labelWidth={14} tooltip="How many seconds to retrieve of historical data when first connecting to the cache server">
        <Input data-testid="seconds" onChange={onSecondsChange} value={seconds} type="number" step={1} />
      </InlineField>
    </Stack>
  );
}
