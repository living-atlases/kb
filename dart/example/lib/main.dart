import 'package:flutter/material.dart';
import 'package:living_atlas_kb_client/living_atlas_kb_client.dart';

void main() => runApp(const KbExampleApp());

class KbExampleApp extends StatelessWidget {
  const KbExampleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Living Atlas Knowledge Base',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF2c7a4b),
        useMaterial3: true,
      ),
      darkTheme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2c7a4b),
          brightness: Brightness.dark,
        ),
      ),
      home: const KbHomePage(),
    );
  }
}

class KbHomePage extends StatefulWidget {
  const KbHomePage({super.key});

  @override
  State<KbHomePage> createState() => _KbHomePageState();
}

class _KbHomePageState extends State<KbHomePage>
    with SingleTickerProviderStateMixin {
  late final TabController _tc;

  static const _config = KbConfig(baseUrl: 'https://kb.l-a.site');

  @override
  void initState() {
    super.initState();
    _tc = TabController(length: 2, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.primary,
        foregroundColor: colorScheme.onPrimary,
        title: Row(
          children: [
            Icon(Icons.eco, color: colorScheme.onPrimary),
            const SizedBox(width: 8),
            const Text(
              'Living Atlas Knowledge Base',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ],
        ),
        bottom: TabBar(
          controller: _tc,
          labelColor: colorScheme.onPrimary,
          unselectedLabelColor: colorScheme.onPrimary.withOpacity(0.7),
          indicatorColor: colorScheme.onPrimary,
          tabs: const [
            Tab(icon: Icon(Icons.info_outline), text: 'About'),
            Tab(icon: Icon(Icons.chat), text: 'Chat'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tc,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          const _AboutTab(),
          KbChatWidget(config: _config),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }
}

// ---------------------------------------------------------------------------
// About Tab
// ---------------------------------------------------------------------------

class _AboutTab extends StatefulWidget {
  const _AboutTab();

  @override
  State<_AboutTab> createState() => _AboutTabState();
}

class _AboutTabState extends State<_AboutTab> {
  static const _config = KbConfig(baseUrl: 'https://kb.l-a.site');
  late Future<ReposManifest> _manifest;

  @override
  void initState() {
    super.initState();
    _manifest = _load();
  }

  Future<ReposManifest> _load() => KbClient(config: _config).listRepos();

  void _retry() => setState(() => _manifest = _load());

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SectionHeader(
                icon: Icons.storage,
                title: 'What is this?',
              ),
              const SizedBox(height: 8),
              Text(
                'The Living Atlas Knowledge Base is a semantic search service '
                'built on top of documentation, configuration files, and source '
                'code from ALA and GBIF repositories. Ask natural language '
                'questions about deployment, configuration, and troubleshooting '
                'of Living Atlas services.',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 32),
              FutureBuilder<ReposManifest>(
                future: _manifest,
                builder: (context, snap) {
                  if (snap.connectionState != ConnectionState.done) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  if (snap.hasError) {
                    return _ReposError(error: snap.error!, onRetry: _retry);
                  }
                  final m = snap.data!;
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _SectionHeader(
                          icon: Icons.star, title: 'Tier 1 Repositories'),
                      const SizedBox(height: 8),
                      _RepoTable(repos: m.tier1),
                      const SizedBox(height: 32),
                      _SectionHeader(
                          icon: Icons.storage, title: 'Other Repositories'),
                      const SizedBox(height: 8),
                      _RepoTable(repos: m.others),
                    ],
                  );
                },
              ),
              const SizedBox(height: 32),
              _SectionHeader(
                icon: Icons.add_circle_outline,
                title: 'Add a Repository',
              ),
              const SizedBox(height: 8),
              _AddRepoSection(),
              const SizedBox(height: 32),
              _SectionHeader(icon: Icons.api, title: 'API'),
              const SizedBox(height: 8),
              _ApiSection(),
              const SizedBox(height: 32),
              _SectionHeader(
                icon: Icons.hub,
                title: 'MCP Integration',
              ),
              const SizedBox(height: 8),
              const _McpSection(),
              const SizedBox(height: 48),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;

  const _SectionHeader({required this.icon, required this.title});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, color: colorScheme.primary, size: 22),
        const SizedBox(width: 8),
        Text(
          title,
          style: Theme.of(context)
              .textTheme
              .titleLarge
              ?.copyWith(color: colorScheme.primary, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Repo tables
// ---------------------------------------------------------------------------

class _RepoTable extends StatelessWidget {
  final List<RepoEntry> repos;

  const _RepoTable({required this.repos});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    if (repos.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Text(
          'No repositories.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Table(
          columnWidths: const {
            0: FlexColumnWidth(2),
            1: FlexColumnWidth(3),
            2: FlexColumnWidth(5),
          },
          border: TableBorder(
            horizontalInside: BorderSide(color: colorScheme.outlineVariant),
          ),
          children: [
            TableRow(
              decoration: BoxDecoration(color: colorScheme.surfaceVariant),
              children: [
                _th(context, 'Org'),
                _th(context, 'Repository'),
                _th(context, 'Description'),
              ],
            ),
            for (final r in repos)
              TableRow(
                children: [
                  _td(context, r.org),
                  _tdLink(context, r.name, r.url),
                  _td(context, r.description ?? ''),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _th(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Text(text,
            style: Theme.of(context)
                .textTheme
                .labelMedium
                ?.copyWith(fontWeight: FontWeight.bold)),
      );

  Widget _td(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Text(text, style: Theme.of(context).textTheme.bodySmall),
      );

  Widget _tdLink(BuildContext context, String text, String url) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: SelectableText(
          text,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.primary,
                decoration: TextDecoration.underline,
              ),
        ),
      );
}

class _ReposError extends StatelessWidget {
  final Object error;
  final VoidCallback onRetry;

  const _ReposError({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.error_outline,
                color: Theme.of(context).colorScheme.onErrorContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Could not load repository list: $error',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onErrorContainer,
                    ),
              ),
            ),
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Add Repo section
// ---------------------------------------------------------------------------

class _AddRepoSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.secondaryContainer,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'To add a repository to the KB, open a Pull Request editing '
              'ansible/repos.yml in the living-atlas-kb repo. Add the repo '
              'name under its org:',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 12),
            _CodeBlock('''
orgs:
  AtlasOfLivingAustralia:
    base_url: https://github.com/AtlasOfLivingAustralia
    repos:
      - my-service                     # simple entry
      - name: my-service               # entry with overrides
        branch: develop
        description: Short description'''),
            const SizedBox(height: 12),
            Text(
              'Tier 1 repos are indexed first during initial setup. All repos '
              'are then re-indexed on demand by the watcher (hourly poll of '
              'commits, GitHub releases and issues/PRs).',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _CodeBlock extends StatelessWidget {
  final String code;
  const _CodeBlock(this.code);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: colorScheme.outlineVariant),
      ),
      child: SelectableText(
        code,
        style: const TextStyle(
          fontFamily: 'monospace',
          fontSize: 12,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// MCP section
// ---------------------------------------------------------------------------

class _McpSection extends StatelessWidget {
  const _McpSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Connect any MCP-capable AI assistant to query the KB directly.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        const _McpCard(
          tool: 'Claude Desktop',
          file: 'claude_desktop_config.json',
          hint:
              'macOS: ~/Library/Application Support/Claude/\n'
              'Windows: %APPDATA%\\Claude\\\n'
              'Linux: ~/.config/Claude/',
          code: '{\n'
              '  "mcpServers": {\n'
              '    "living-atlas-kb": {\n'
              '      "type": "http",\n'
              '      "url": "https://kb.l-a.site/mcp"\n'
              '    }\n'
              '  }\n'
              '}',
        ),
        const SizedBox(height: 8),
        const _McpCard(
          tool: 'OpenCode / Claude Code',
          file: '~/.config/opencode/opencode.json',
          code: '{\n'
              '  "mcp": {\n'
              '    "servers": {\n'
              '      "living-atlas-kb": {\n'
              '        "type": "http",\n'
              '        "url": "https://kb.l-a.site/mcp"\n'
              '      }\n'
              '    }\n'
              '  }\n'
              '}',
        ),
        const SizedBox(height: 8),
        const _McpCard(
          tool: 'Cursor',
          file: '.cursor/mcp.json',
          code: '{\n'
              '  "mcpServers": {\n'
              '    "living-atlas-kb": {\n'
              '      "type": "http",\n'
              '      "url": "https://kb.l-a.site/mcp"\n'
              '    }\n'
              '  }\n'
              '}',
        ),
        const SizedBox(height: 8),
        const _McpCard(
          tool: 'VS Code (GitHub Copilot)',
          file: '.vscode/settings.json',
          code: '{\n'
              '  "github.copilot.chat.mcp.servers": {\n'
              '    "living-atlas-kb": {\n'
              '      "type": "http",\n'
              '      "url": "https://kb.l-a.site/mcp"\n'
              '    }\n'
              '  }\n'
              '}',
        ),
      ],
    );
  }
}

class _McpCard extends StatelessWidget {
  final String tool;
  final String file;
  final String code;
  final String? hint;

  const _McpCard({
    required this.tool,
    required this.file,
    required this.code,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              tool,
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              file,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                    color: colorScheme.primary,
                  ),
            ),
            if (hint != null) ...[
              const SizedBox(height: 4),
              Text(
                hint!,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
              ),
            ],
            const SizedBox(height: 8),
            _CodeBlock(code),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// API section
// ---------------------------------------------------------------------------

class _ApiSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Base URL: https://kb.l-a.site',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(fontFamily: 'monospace'),
        ),
        const SizedBox(height: 12),
        const _ApiEndpoint(
          method: 'POST',
          path: '/api/query',
          description: 'Semantic search. Body: question, collection, n_results, '
              'content_type (optional: source, release, issue, pr, wiki, faq)',
          example: '{"question": "how to configure collectory", '
              '"n_results": 5}',
        ),
        const SizedBox(height: 8),
        const _ApiEndpoint(
          method: 'POST',
          path: '/api/chat',
          description: 'LLM-powered chat with KB context (SSE streaming)',
          example: '{"question": "How do I install biocache-service?", '
              '"collection": "la_toolkit_kb"}',
        ),
        const SizedBox(height: 8),
        const _ApiEndpoint(
          method: 'GET',
          path: '/api/collections',
          description: 'List available ChromaDB collections',
          example: 'GET /api/collections',
        ),
        const SizedBox(height: 8),
        const _ApiEndpoint(
          method: 'GET',
          path: '/api/versions',
          description: 'Latest release/version per component (from GitHub '
              'Releases); add /{org}/{name} for one component',
          example: 'GET /api/versions/AtlasOfLivingAustralia/collectory',
        ),
      ],
    );
  }
}

class _ApiEndpoint extends StatelessWidget {
  final String method;
  final String path;
  final String description;
  final String example;

  const _ApiEndpoint({
    required this.method,
    required this.path,
    required this.description,
    required this.example,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final methodColor = method == 'GET' ? Colors.green.shade700 : Colors.blue.shade700;

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: methodColor.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    method,
                    style: TextStyle(
                      color: methodColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                SelectableText(
                  path,
                  style: const TextStyle(
                      fontFamily: 'monospace', fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(description,
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 6),
            _CodeBlock(example),
          ],
        ),
      ),
    );
  }
}
