/** Transport envelope shared by ShenZhi Backend module clients. */
export interface ApiEnvelope<T> {
  code: number;
  data?: T;
  message?: string;
}
