import { DataSourcePlugin } from '@grafana/data';
import { ConfigEditor } from './ConfigEditor';
import { DataSource } from './DataSource';
import { QueryEditor } from './QueryEditor';
import { OpenRVDASDataSourceOptions, OpenRVDASQuery } from './types';

export const plugin = new DataSourcePlugin<DataSource, OpenRVDASQuery, OpenRVDASDataSourceOptions>(DataSource)
  .setConfigEditor(ConfigEditor)
  .setQueryEditor(QueryEditor);
