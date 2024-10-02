import React, { ChangeEvent } from 'react';
import { DataSourcePluginOptionsEditorProps } from '@grafana/data';
import { InlineField, Input } from '@grafana/ui';
import { OpenRVDASDataSourceOptions } from './types';

interface Props extends DataSourcePluginOptionsEditorProps<OpenRVDASDataSourceOptions> {}

export function ConfigEditor(props: Props) {
  const { options } = props;
  const { jsonData } = options;

  const onURLChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { onOptionsChange, options } = props;
    const jsonData = {
      ...options.jsonData,
      url: event.target.value,
    };
    onOptionsChange({ ...options, jsonData });
  };

  return (
    <InlineField label="Websocket URL" labelWidth={18} tooltip="Supported schemes: WebSocket (ws://)">
      <Input
        width={50}
        name="url"
        data-testid="uri-websocket-server"
        value={jsonData.url || ''}
        autoComplete="off"
        placeholder="ws://localhost/cds-ws"
        onChange={onURLChange}
      />
    </InlineField>
  );
}
