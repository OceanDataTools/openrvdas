import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

export interface OpenRVDASQuery extends DataQuery {
  fields?: string;
  seconds?: number;
  backRecords?: number;
  interval: number
  scopedVars: any;
}

export const defaultQuery: Partial<OpenRVDASQuery> = {
  backRecords: 1,
  interval: 1,
};

/**
 * These are options configured for each DataSource instance
 */
export interface OpenRVDASDataSourceOptions extends DataSourceJsonData {
  url?: string;
}
