import type { JsonValue, TSchema } from '@earendil-works/pi-ai'

import type {
  AgentActivation,
  AgentContextSnapshot,
  AgentToolResult,
  AgentYieldContract,
  ToolContract,
  ToolInvocation,
} from '../../shared/generated/contracts.js'
import type {
  PiActivationEnvironmentV2,
  PiRuntimeHostV2,
  PiRuntimeProviderV2,
  PiRuntimeToolDefinitionV2,
} from './pi-runtime-v2.js'

export interface PiRuntimeCoreBridgeV2 {
  request(method: string, params?: JsonValue, timeoutMs?: number): Promise<unknown>
}

export class PiRuntimeHostV2ProtocolError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new PiRuntimeHostV2ProtocolError('PI_V2_HOST_PROTOCOL_INVALID', `${label} was invalid.`)
  }
  return value as Record<string, unknown>
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new PiRuntimeHostV2ProtocolError('PI_V2_HOST_PROTOCOL_INVALID', `${label} was invalid.`)
  }
  return value
}

function json(value: unknown, label: string): JsonValue {
  try {
    return JSON.parse(JSON.stringify(value)) as JsonValue
  } catch {
    throw new PiRuntimeHostV2ProtocolError('PI_V2_HOST_PROTOCOL_INVALID', `${label} was not JSON.`)
  }
}

function active(signal: AbortSignal): void {
  if (signal.aborted) {
    throw new PiRuntimeHostV2ProtocolError('PI_V2_HOST_ABORTED', 'The activation was cancelled.')
  }
}

function provider(value: unknown): PiRuntimeProviderV2 {
  const payload = record(value, 'provider runtime')
  return {
    baseUrl: string(payload.base_url, 'provider base URL'),
    modelId: string(payload.model_id, 'provider model ID'),
    apiKey: string(payload.api_key, 'provider API key'),
  }
}

function environment(
  value: unknown,
  runtimeProvider: PiRuntimeProviderV2,
): PiActivationEnvironmentV2 {
  const payload = record(value, 'activation environment')
  const rawTools = payload.tools
  if (!Array.isArray(rawTools)) {
    throw new PiRuntimeHostV2ProtocolError('PI_V2_HOST_PROTOCOL_INVALID', 'Tools were invalid.')
  }
  const tools: PiRuntimeToolDefinitionV2[] = rawTools.map((item) => {
    const definition = record(item, 'tool definition')
    return {
      contract: record(definition.contract, 'tool contract') as ToolContract,
      inputSchema: record(definition.input_schema, 'tool input schema') as TSchema,
    }
  })
  return {
    context: record(payload.context, 'Agent context') as AgentContextSnapshot,
    systemPrompt: string(payload.system_prompt, 'system prompt'),
    provider: runtimeProvider,
    yieldSchema: record(payload.yield_schema, 'yield schema') as TSchema,
    tools,
  }
}

/** Main-owned bridge: Core supplies authority; provider secrets stay in Main memory only. */
export class CorePiRuntimeHostV2 implements PiRuntimeHostV2 {
  private readonly preparedActivations = new Set<string>()

  constructor(
    private readonly core: PiRuntimeCoreBridgeV2,
    private readonly projectId: string,
  ) {
    string(projectId, 'project ID')
  }

  async prepare(
    activation: AgentActivation,
    signal: AbortSignal,
  ): Promise<PiActivationEnvironmentV2> {
    active(signal)
    const [prepared, providerValue] = await Promise.all([
      this.core.request(
        'agent.activations.prepare',
        { project_id: this.projectId, activation_id: activation.activation_id },
        15_000,
      ),
      this.core.request('provider.runtime.get', {}, 10_000),
    ])
    active(signal)
    const result = environment(prepared, provider(providerValue))
    if (result.context.project_id !== this.projectId) {
      throw new PiRuntimeHostV2ProtocolError(
        'PI_V2_HOST_PROJECT_MISMATCH',
        'Core returned an activation context for another project.',
      )
    }
    this.preparedActivations.add(activation.activation_id)
    return result
  }

  async invokeTool(
    invocation: ToolInvocation,
    argumentsValue: JsonValue,
    signal: AbortSignal,
  ): Promise<AgentToolResult> {
    active(signal)
    if (!this.preparedActivations.has(invocation.activation_id)) {
      throw new PiRuntimeHostV2ProtocolError(
        'PI_V2_HOST_ACTIVATION_UNKNOWN',
        'The activation was not prepared by this Main process.',
      )
    }
    const value = await this.core.request(
      'agent.tools.invoke',
      {
        project_id: this.projectId,
        invocation: json(invocation, 'tool invocation'),
        arguments: argumentsValue,
      },
      15_000,
    )
    active(signal)
    return record(value, 'tool result') as AgentToolResult
  }

  async validateYield(
    activation: AgentActivation,
    candidate: JsonValue,
    signal: AbortSignal,
  ): Promise<AgentYieldContract> {
    active(signal)
    if (!this.preparedActivations.has(activation.activation_id)) {
      throw new PiRuntimeHostV2ProtocolError(
        'PI_V2_HOST_ACTIVATION_UNKNOWN',
        'The activation was not prepared by this Main process.',
      )
    }
    const value = await this.core.request(
      'agent.yields.validate',
      {
        project_id: this.projectId,
        activation_id: activation.activation_id,
        yield: candidate,
      },
      15_000,
    )
    active(signal)
    return record(value, 'Agent yield') as AgentYieldContract
  }
}
