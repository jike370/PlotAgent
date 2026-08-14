const previewModules = import.meta.glob<string>('../assets/chart-previews/*.png', {
  eager: true,
  import: 'default',
  query: '?url',
})

export const chartPreviewAssets: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(Object.entries(previewModules).map(([path, url]) => {
    const match = /\/([^/]+)\.png$/.exec(path)
    if (!match) throw new Error(`Invalid chart preview asset path: ${path}`)
    return [match[1], url]
  })),
)

export function chartPreviewSource(profileId: string): string {
  const source = chartPreviewAssets[profileId]
  if (!source) throw new Error(`Missing chart preview asset for ${profileId}`)
  return source
}
