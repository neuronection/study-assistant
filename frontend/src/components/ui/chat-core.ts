export {
  useChatStream,
  liveTurnReducer,
  initialLiveTurnState,
  buildBranchTree,
  linearTree,
  walkActivePath,
  activePathSet,
  variantInfo,
} from '@neuronection/assistant-ui/chat-core'
export type {
  BranchTree,
  BranchNode,
  BranchNodeInput,
} from '@neuronection/assistant-ui/chat-core'
export type {
  ChatRole,
  ChatMessageStatus,
  ChatError,
  ChatMessageVariants,
  ChatAttachmentView,
  ChatMessageView,
  FlowStepInfo,
  ChatStreamEvent,
  ChatStreamTransport,
  LiveTurnAction,
  LiveTurnState,
  LiveTurnStatus,
  LiveNodeState,
  LiveToolCall,
  UseChatStreamOptions,
  UseChatStreamResult,
} from '@neuronection/assistant-ui/chat-core'
