export interface FetchedReview {
  externalId: string;
  rawText: string;
  author: string;
  rating: number | null;
  postedAt: Date | null;
  url: string | null;
  meta: Record<string, unknown>;
}

export interface SourceRow {
  id: number;
  name: string;
  kind: string;
  config_json: Record<string, any>;
}
