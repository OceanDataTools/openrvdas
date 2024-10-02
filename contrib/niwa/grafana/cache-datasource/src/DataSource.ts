import {
  AnnotationQuery,
  CircularDataFrame,
  CoreApp,
  DataFrameView,
  DataQueryRequest,
  DataQueryResponse,
  DataSourceApi,
  DataSourceInstanceSettings,
  FieldType,
  LoadingState,
  Field,
  AnnotationEvent,
  rangeUtil
} from '@grafana/data';
import { getTemplateSrv, TemplateSrv } from '@grafana/runtime';
import { lastValueFrom, merge, Observable } from 'rxjs';
import { defaultQuery, OpenRVDASDataSourceOptions, OpenRVDASQuery } from './types';
import { AnnotationQueryEditor } from 'AnnotationQueryEditor';

export class DataSource extends DataSourceApi<OpenRVDASQuery, OpenRVDASDataSourceOptions> {
  serverURL?: string;
  connections: {[key: string]: WebSocket} = {};
  templateSrv: TemplateSrv = getTemplateSrv();

  constructor(instanceSettings: DataSourceInstanceSettings<OpenRVDASDataSourceOptions>) {
    super(instanceSettings);

    this.serverURL = instanceSettings.jsonData.url || 'ws://localhost/cds-ws';
  }

  getDefaultQuery(app: CoreApp): Partial<OpenRVDASQuery> {
    return defaultQuery;
  }

  query(options: DataQueryRequest<OpenRVDASQuery>): Observable<DataQueryResponse> {

    console.log("Query request", options);
    this.templateSrv.getVariables().map((variable: any) => {
      options.scopedVars[variable.name] = {
        // weird but we need the field names as the output not ids
        text: variable.current.value,
        value: variable.current.text
      }
    })

    const observables = options.targets.map((query) => {

      query.fields = this.templateSrv.replace(query.fields, options.scopedVars);
      console.log("parsed query", query.fields);

      return new Observable<DataQueryResponse>((subscriber) => {
        const frame = new CircularDataFrame({
          append: 'tail',
          capacity: 1000000,
        });

        frame.refId = query.refId;
        frame.addField({ name: 'time', type: FieldType.time });
        let connection = this.connections[options.requestId];
        
        if(connection) {
          // this should only be when stopping the live preview in explore
          // otherwise it stays open after you leave explore!
          connection.close();
        }
        
        connection = new WebSocket(this.serverURL || '');

        // register the cache fields we want data for
        connection.onopen = () => {
          connection.send(JSON.stringify(this.buildSubscribeMessage(query)));
        }
        connection.onerror = (error: any) => {
          console.error(`WebSocket error: ${JSON.stringify(error)}`);
        };

        connection.onmessage = (event: any) => {
          const response = JSON.parse(event.data);
          
          if(response.data) {
            
            const formattedData = {time: 0} as any;
            Object.keys(response.data).map((field) => {
              // include data from previous "seconds", likely to happen with high frequency data and slower interval
              response.data[field].map((cacheData: any) => {
                this.formatCacheData(cacheData, formattedData, frame, field);
                if(formattedData.time !== 0 && Object.keys(formattedData).length > 1) {
                  // avoid forwarding cache responses with no new data
                  frame.add(formattedData);
                }
              })
            })

            if(formattedData.time !== 0 && Object.keys(formattedData).length > 1) {
              // avoid forwarding cache responses with no new data
              subscriber.next({
                data: [frame],
                key: query.refId,
                state: LoadingState.Streaming,
              });
            }
          }

          // ask for next available data
          connection.send(JSON.stringify({"type": "ready"}))
        };
      });
    });

    return merge(...observables);
  }


  formatCacheData(cacheData: any, formattedData: any, frame: any, field: string): any {
    formattedData.time = Math.max(parseFloat(cacheData[0]) * 1000, formattedData.time);

    let parsedValue = parseFloat(cacheData[1]);
    let fieldType = FieldType.number;

    if(isNaN(parsedValue)) {
      parsedValue = cacheData[1];
      fieldType = FieldType.string;
    }

    if(!this.ifFieldExists(frame, field)) {
      frame.addField({ name: field, type: fieldType });
    }

    formattedData[field] = parsedValue;

    return formattedData
  }


  ifFieldExists(frame: CircularDataFrame, name: string): Boolean {
    return frame.fields?.find((field: Field<any>) => {
      return field.name === name;
    }) != null;
  }


  buildSubscribeMessage(query: OpenRVDASQuery): any {
    const message = {
      'type':'subscribe',
      'interval': query.interval || 1,
      'fields': query.fields?.split(",").reduce((agg: any, field: string) => {
        agg[field] = {
          'seconds': query.seconds || 1,
          'back_records': query.backRecords || 1,
        };
        return agg;
      } , {} as any)
    }

    return message
  }


  async testDatasource() {
    // Implement a health check for your data source.
    // TODO: check websocket connection here
    return {
      status: 'success',
      message: 'Success',
    };
  }


  filterQuery(query: OpenRVDASQuery): boolean {
    // return false to stop the query
    return query.fields?.length !== 0;
  }


  getQueryDisplayText(query: OpenRVDASQuery) {
    return JSON.stringify(this.buildSubscribeMessage(query), null, 3);
  }

  // TODO: remove or replace these annotation methods, doesn't seem to be possible to do streaming annotations
  // instead need to do a one-off query of cache for the time-period needed
  annotations = {
      QueryEditor: AnnotationQueryEditor,
      prepareQuery: this.prepareQuery
    };

  prepareQuery(annotation: AnnotationQuery<OpenRVDASQuery>): OpenRVDASQuery | undefined {
    const { fields } = annotation;

    if (!fields) {
      return undefined
    }

    return annotation.target
    //return {...annotation, refId: annotation.name, fields: fields, seconds: seconds }
  }

  async annotationQuery(options: any): Promise<AnnotationEvent[]> {
    const { fields, seconds, interval } = options.annotation;

    if (!fields) {
      return [];
    }

    const id = `annotation-${options.annotation.name}`;

    const query: OpenRVDASQuery = {
      refId: id,
      scopedVars: {},
      fields,
      seconds,
      interval,
    };

    const intervalInfo = rangeUtil.calculateInterval(options.range, 1);
    const request = {
      targets: [query],
      requestId: id,
      interval: intervalInfo.interval,
      intervalMs: intervalInfo.intervalMs,
      range: options.range,
      scopedVars: {},
      timezone: 'UTC',
      app: CoreApp.Dashboard,
      startTime: Date.now(),
      hideFromInspector: false
    } as  DataQueryRequest<OpenRVDASQuery> 

    // get data

    const { data } = await lastValueFrom(this.query(request));

    const annotations: AnnotationEvent[] = [];
    const splitFields: string[] = fields.split(',').filter((v: string) => v !== '');

    const titleField = splitFields.splice(0, 1)[0];

    for (const frame of data) {
      const view = new DataFrameView<any>(frame);

      view.forEach((row) => {
        // TODO: make text format configurable
        annotations.push({
          time: new Date(row.Time).valueOf(),
          title: row[titleField],
          text: splitFields.map((field: string) => row[field]).join(" | ")
        });
      });
    }

    return annotations;
  }
}
