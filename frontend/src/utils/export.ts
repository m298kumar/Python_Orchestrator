/**
 * Export data as a downloadable CSV or JSON file.
 */

export function exportToCSV(
  data: object[],
  filename: string,
): void {
  if (data.length === 0) return;

  const headers = Object.keys(data[0]);
  const csvRows = [
    headers.join(','),
    ...data.map((row) =>
      headers
        .map((h) => {
          const val = String((row as Record<string, unknown>)[h] ?? '');
          return val.includes(',') || val.includes('"') || val.includes('\n')
            ? `"${val.replace(/"/g, '""')}"`
            : val;
        })
        .join(','),
    ),
  ];

  downloadBlob(csvRows.join('\n'), filename, 'text/csv;charset=utf-8;');
}

export function exportToJSON<T>(data: T[], filename: string): void {
  downloadBlob(JSON.stringify(data, null, 2), filename, 'application/json');
}

function downloadBlob(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
