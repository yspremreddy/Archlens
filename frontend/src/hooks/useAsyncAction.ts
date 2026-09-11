import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/**
 * Wraps a single in-flight fetch-backed action with loading/error state
 * and cancellation. Calling `run` again (or unmount) aborts any previous
 * in-flight request via AbortController, so a stale response can never
 * overwrite a newer one.
 */
export function useAsyncAction<Args extends unknown[], T>(
  action: (signal: AbortSignal, ...args: Args) => Promise<T>,
) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: false, error: null })
  const controllerRef = useRef<AbortController | null>(null)

  const run = useCallback(
    async (...args: Args) => {
      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller
      setState({ data: null, loading: true, error: null })
      try {
        const data = await action(controller.signal, ...args)
        if (!controller.signal.aborted) setState({ data, loading: false, error: null })
        return data
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return undefined
        const message = err instanceof ApiError ? err.message : 'Unexpected error'
        setState({ data: null, loading: false, error: message })
        return undefined
      }
    },
    [action],
  )

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    setState((s) => ({ ...s, loading: false }))
  }, [])

  return { ...state, run, cancel }
}
