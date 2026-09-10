import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { buildBranchTree, type BranchTree } from '@/components/ui/chat-core'
import { ChatBranchTree } from '@/components/ui/chat-branch-tree'
import { PopoverButton } from '@/components/ui/popover-button'
import { getChatBranchTree, selectChatVariant } from '@/lib/api'

function toBranchTree(data: Awaited<ReturnType<typeof getChatBranchTree>>): BranchTree {
  return buildBranchTree({
    activeRootId: data.active_root_id !== null ? String(data.active_root_id) : null,
    nodes: data.nodes.map((node) => ({
      id: String(node.id),
      role: node.role === 'user' ? 'user' : 'assistant',
      excerpt: node.excerpt,
      parentId: node.parent_id !== null ? String(node.parent_id) : null,
      activeChildId: node.active_child_id !== null ? String(node.active_child_id) : null,
    })),
  })
}

export function BranchTreeButton({ sessionId }: { sessionId: number }) {
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
  const branchTree = tree.data !== undefined ? toBranchTree(tree.data) : null
  return (
    <PopoverButton
      label={t('chat.tree.title')}
      side="bottom"
      align="end"
      panelClassName="w-80 p-0"
      trigger={<GitBranch className="size-4" aria-hidden />}
      triggerClassName="size-8"
    >
      {branchTree !== null ? (
        <ChatBranchTree
          tree={branchTree}
          onSelect={(id) => selectNode.mutate(Number(id))}
          labels={{
            tree: t('chat.tree.title'),
            user: t('chat.treeUser'),
            assistant: t('chat.treeAssistant'),
            forked: (count) => t('chat.treeForked', { count }),
          }}
        />
      ) : (
        <p className="text-muted-foreground p-3 text-xs">{t('chat.tree.empty')}</p>
      )}
    </PopoverButton>
  )
}
