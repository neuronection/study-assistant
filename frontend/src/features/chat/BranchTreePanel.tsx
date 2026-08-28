import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, MessageSquare, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Popover } from '@/components/ui/popover'
import {
  getChatBranchTree,
  selectChatVariant,
  type ChatBranchNode,
  type ChatBranchTree,
} from '@/lib/api'

import { cn } from '@/lib/utils'

function useActivePath(tree: ChatBranchTree | undefined): Set<number> {
  const path = new Set<number>()
  if (!tree) {
    return path
  }
  const byId = new Map(tree.nodes.map((node) => [node.id, node]))
  let currentId: number | null =
    tree.active_root_id !== null &&
    tree.nodes.some((node) => node.id === tree.active_root_id)
      ? tree.active_root_id
      : (tree.nodes[0]?.id ?? null)
  while (currentId !== null) {
    const node = byId.get(currentId)
    if (!node) {
      break
    }
    path.add(node.id)
    currentId = node.active_child_id
  }
  return path
}

function TreeNodeRow({
  node,
  depth,
  tree,
  activePath,
  onSelect,
}: {
  node: ChatBranchNode
  depth: number
  tree: ChatBranchTree
  activePath: Set<number>
  onSelect: (id: number) => void
}) {
  const isActive = activePath.has(node.id)
  const childNodes = node.children
    .map((id) => tree.nodes.find((entry) => entry.id === id))
    .filter((entry): entry is ChatBranchNode => entry !== undefined)
  return (
    <div>
      <button
        type="button"
        role="treeitem"
        aria-current={isActive ? 'true' : undefined}
        className={cn(
          'hover:bg-subtle flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left transition-colors',
          isActive ? 'text-foreground' : 'text-muted-foreground',
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
        onClick={() => onSelect(node.id)}
        title={node.excerpt || `#${node.id}`}
      >
        <span
          aria-hidden
          className={cn(
            'border-muted-foreground bg-surface inline-block size-2 shrink-0 rounded-full border',
            isActive && 'bg-primary border-primary',
          )}
        />
        {node.role === 'user' ? (
          <MessageSquare className="size-3 shrink-0" aria-hidden />
        ) : (
          <Sparkles className="size-3 shrink-0" aria-hidden />
        )}
        <span className={cn('min-w-0 truncate text-xs', isActive && 'font-semibold')}>
          {node.excerpt || `#${node.id}`}
        </span>
        {node.children.length > 1 ? (
          <span className="text-muted-foreground ml-auto shrink-0 text-[10px]">
            {node.children.length}
          </span>
        ) : null}
      </button>
      {childNodes.length > 0 ? (
        <div className="border-border/70 ml-3 border-l pl-1.5">
          {childNodes.map((child) => (
            <TreeNodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              tree={tree}
              activePath={activePath}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function BranchTreePanel({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const tree = useQuery({
    queryKey: ['chat-branch-tree', sessionId],
    queryFn: () => getChatBranchTree(sessionId),
  })
  const selectNode = useMutation({
    mutationFn: (messageId: number) => selectChatVariant(messageId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] })
      void queryClient.invalidateQueries({ queryKey: ['chat-branch-tree', sessionId] })
    },
  })
  const activePath = useActivePath(tree.data)
  const roots = tree.data?.nodes.filter((node) => node.parent_id === null) ?? []
  return (
    <div className="max-h-[24rem] w-72 overflow-y-auto">
      {roots.length === 0 ? (
        <p className="text-muted-foreground p-3 text-xs">{t('chat.tree.empty')}</p>
      ) : (
        <div className="p-1.5" role="tree" aria-label={t('chat.tree.title')}>
          {(tree.data as ChatBranchTree).nodes.length > 0
            ? roots.map((root) => (
                <TreeNodeRow
                  key={root.id}
                  node={root}
                  depth={0}
                  tree={tree.data as ChatBranchTree}
                  activePath={activePath}
                  onSelect={(id) => selectNode.mutate(id)}
                />
              ))
            : null}
        </div>
      )}
    </div>
  )
}

export function BranchTreeButton({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  return (
    <Popover
      label={t('chat.tree.title')}
      side="bottom"
      align="end"
      panelClassName="w-80 p-0"
      trigger={<GitBranch className="size-4" aria-hidden />}
      triggerClassName="size-8"
    >
      <BranchTreePanel sessionId={sessionId} />
    </Popover>
  )
}
