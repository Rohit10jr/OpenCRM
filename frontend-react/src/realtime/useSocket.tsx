import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSession } from '@/auth/session'
import { keys } from '@/api/queryKeys'
import { initSocket, type CrmSocket, type SocketHandler } from './socket'

/**
 * The React binding for the ported socket.
 *
 * The socket itself is framework-agnostic and stays that way — this file is the only
 * place that knows about React or about TanStack Query, which is what made the port a
 * port. Everything below is new; nothing below is reconnect logic.
 */

const SocketContext = createContext<CrmSocket | null>(null)

export function SocketProvider({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useSession()
  const queryClient = useQueryClient()
  const [socket, setSocket] = useState<CrmSocket | null>(null)

  useEffect(() => {
    // No session, no socket: `connect()` returns immediately without a token, and holding
    // a dead client would make `connected` lie to anything that reads it.
    if (!isLoggedIn) {
      setSocket(null)
      return
    }

    const client = initSocket(() => {
      // The server does not know our query keys, so a `refetch_resource` frame cannot name
      // one. Refetching every document is the conservative read of "something you cached
      // is stale" — and it is rare enough that being broad costs nothing.
      queryClient.invalidateQueries({ queryKey: keys.doc.all })
    })
    setSocket(client)
    return () => client.close()
  }, [isLoggedIn, queryClient])

  return <SocketContext.Provider value={socket}>{children}</SocketContext.Provider>
}

export function useSocket() {
  return useContext(SocketContext)
}

/**
 * Subscribe to one event for as long as the component is mounted.
 *
 * The handler goes through a ref so that re-registering is not necessary when a caller
 * passes an inline function — which every caller does. Without it, every render would
 * `off` and `on` again, and a render during a burst of frames could drop one.
 */
export function useSocketEvent(event: string, handler: SocketHandler) {
  const socket = useSocket()
  const latest = useRef(handler)
  latest.current = handler

  useEffect(() => {
    if (!socket) return
    const stable: SocketHandler = (payload) => latest.current(payload)
    socket.on(event, stable)
    return () => {
      socket.off(event, stable)
    }
  }, [socket, event])
}

/**
 * Keep one document live: subscribe on mount, unsubscribe on unmount, and refetch it when
 * the server says it changed.
 *
 * `doc_unsubscribe` on unmount is not just tidiness — the socket replays its subscription
 * set on every reconnect, so a subscription left behind is replayed forever, and after a
 * few navigations a reconnect would re-subscribe to every record the user ever opened.
 */
export function useDocSubscription(doctype: string, name: string | undefined) {
  const socket = useSocket()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!socket || !name) return
    socket.emit('doc_subscribe', doctype, name)
    return () => {
      socket.emit('doc_unsubscribe', doctype, name)
    }
  }, [socket, doctype, name])

  useSocketEvent('docinfo_update', () => {
    if (!name) return
    queryClient.invalidateQueries({ queryKey: keys.doc.one(doctype, name) })
    queryClient.invalidateQueries({ queryKey: ['activities', name] })
  })
}
