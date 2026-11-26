/** Paging of the Quote list: the page number in the URL, and how many pages the API's total makes. */

export function parsePage(raw: string | string[] | undefined): number {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (value === undefined || !/^[1-9]\d{0,8}$/.test(value)) {
    return 1;
  }
  return Number(value);
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}
