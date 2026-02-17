export interface GcsListResponse {
  images: string[];
  total: number;
  page: number;
  total_pages: number;
}

export async function listImages(
  prefix: string,
  page = 0,
  pageSize = 20
): Promise<GcsListResponse> {
  const params = new URLSearchParams({
    prefix,
    page: String(page),
    page_size: String(pageSize),
  });
  const res = await fetch(`/api/gcs/list?${params}`);
  if (!res.ok) throw new Error(`GCS list failed: ${res.statusText}`);
  return res.json();
}

export function thumbnailUrl(uri: string): string {
  return `/api/gcs/thumbnail?uri=${encodeURIComponent(uri)}`;
}
