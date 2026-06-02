import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { createServer } from 'http'

const PORT = 8788

const mcp = new Server(
  { name: 'webhook', version: '0.0.1' },
  {
    capabilities: { experimental: { 'claude/channel': {} } },
    instructions: 'GitHub Actions webhook notifications arrive as <channel source="webhook">. Read and act on them.',
  }
)

await mcp.connect(new StdioServerTransport())

createServer(async (req, res) => {
  let body = ''
  req.on('data', chunk => { body += chunk })
  req.on('end', async () => {
    await mcp.notification({
      method: 'notifications/claude/channel',
      params: {
        content: body,
        meta: { path: req.url, method: req.method },
      },
    })
    res.writeHead(200)
    res.end('ok')
  })
}).listen(PORT, '127.0.0.1')
