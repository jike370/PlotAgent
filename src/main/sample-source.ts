import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const SAMPLE_CSV = `time_min,fluorescence_au,condition
0,0.142,control
5,0.188,control
10,0.247,control
15,0.331,control
20,0.426,control
25,0.503,control
0,0.154,treated
5,0.223,treated
10,0.318,treated
15,0.441,treated
20,0.574,treated
25,0.681,treated
`

export async function ensureBundledSampleSource(userDataDirectory: string): Promise<string> {
  const directory = join(userDataDirectory, 'bundled-samples')
  const destination = join(directory, 'temperature-response.csv')
  await mkdir(directory, { recursive: true })
  try {
    if (await readFile(destination, 'utf8') === SAMPLE_CSV) return destination
  } catch {
    // The immutable bundled copy is recreated below.
  }
  const temporary = join(directory, `.temperature-response.${process.pid}.tmp`)
  await writeFile(temporary, SAMPLE_CSV, { encoding: 'utf8', mode: 0o600 })
  await rename(temporary, destination)
  return destination
}
