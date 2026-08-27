export type ProviderPresetId = 'zhipu' | 'deepseek' | 'aliyun' | 'custom'

export interface ProviderModelPreset {
  readonly id: string
  readonly name: string
  readonly availability: string
}

export interface ProviderPreset {
  readonly id: Exclude<ProviderPresetId, 'custom'>
  readonly name: string
  readonly baseUrl: string
  readonly description: string
  readonly models: ReadonlyArray<ProviderModelPreset>
}

export const providerPresets: ReadonlyArray<ProviderPreset> = Object.freeze([
  {
    id: 'zhipu',
    name: '智谱开放平台',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    description: '官方免费模型，适合先完成 fig-agent 工具调用检查。',
    models: [
      { id: 'glm-4.7-flash', name: 'GLM-4.7-Flash', availability: '免费' },
    ],
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    description: '按 Token 计费，Flash 型号适合低成本任务编排。',
    models: [
      { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', availability: '低价' },
      { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', availability: '高能力' },
    ],
  },
  {
    id: 'aliyun',
    name: '阿里云百炼',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    description: '新用户模型额度通常限时有效，具体余量以百炼控制台为准。',
    models: [
      { id: 'qwen3.6-flash', name: 'Qwen 3.6 Flash', availability: '新用户限时额度' },
      { id: 'qwen3.7-plus', name: 'Qwen 3.7 Plus', availability: '新用户限时额度' },
      { id: 'qwen3.7-max', name: 'Qwen 3.7 Max', availability: '新用户限时额度' },
    ],
  },
])

export function providerPreset(id: ProviderPresetId): ProviderPreset | undefined {
  return providerPresets.find((item) => item.id === id)
}

export function matchProviderPreset(baseUrl: string | undefined): ProviderPresetId {
  if (!baseUrl) return 'zhipu'
  const normalized = baseUrl.replace(/\/$/, '').toLocaleLowerCase('en-US')
  return providerPresets.find(
    (item) => item.baseUrl.toLocaleLowerCase('en-US') === normalized,
  )?.id ?? 'custom'
}
