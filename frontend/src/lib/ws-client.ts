import { WsClient } from './ws'

let client: WsClient | null = null

export function getWsClient(): WsClient {
  if (client === null) {
    client = WsClient.browser()
  }
  return client
}
