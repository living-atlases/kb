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
            Tab(icon: Icon(Icons.chat), text: 'Chat'),
            Tab(icon: Icon(Icons.info_outline), text: 'About'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tc,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          KbChatWidget(config: _config),
          const _AboutTab(),
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

class _AboutTab extends StatelessWidget {
  const _AboutTab();

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
              _SectionHeader(icon: Icons.star, title: 'Tier 1 Repositories'),
              const SizedBox(height: 8),
              const _RepoTable(repos: _tier1Repos),
              const SizedBox(height: 32),
              _SectionHeader(icon: Icons.storage, title: 'Tier 2 Repositories'),
              const SizedBox(height: 8),
              const _RepoTable(repos: _tier2Repos),
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

class _RepoRow {
  final String org;
  final String repo;
  final String description;

  const _RepoRow(this.org, this.repo, this.description);

  String get url => 'https://github.com/$org/$repo';
}

const _tier1Repos = [
  _RepoRow('AtlasOfLivingAustralia', 'ala-install',
      'Ansible playbooks for full ALA stack deployment'),
  _RepoRow('living-atlases', 'la-toolkit',
      'LA Toolkit — management UI for Living Atlas nodes'),
  _RepoRow('gbif', 'pipelines',
      'GBIF/ALA data processing pipelines (Beam + Spark)'),
];

const _tier2Repos = [
  _RepoRow('AtlasOfLivingAustralia', 'collectory',
      'Metadata registry for collections and data providers'),
  _RepoRow('AtlasOfLivingAustralia', 'biocache-service',
      'Occurrence record search and retrieval API'),
  _RepoRow('AtlasOfLivingAustralia', 'biocache-hubs',
      'Grails web app for occurrence search UI'),
  _RepoRow('AtlasOfLivingAustralia', 'ala-bie-hub',
      'Species pages hub (Grails)'),
  _RepoRow('AtlasOfLivingAustralia', 'spatial-hub',
      'Spatial portal front-end'),
  _RepoRow('AtlasOfLivingAustralia', 'spatial-service',
      'Spatial analysis back-end service'),
  _RepoRow('AtlasOfLivingAustralia', 'image-service',
      'Image storage, serving, and metadata'),
  _RepoRow('AtlasOfLivingAustralia', 'species-list-webapp',
      'Species list management service'),
  _RepoRow('AtlasOfLivingAustralia', 'ala-auth-plugin',
      'CAS authentication plugin'),
  _RepoRow('AtlasOfLivingAustralia', 'userdetails',
      'User profile and roles service'),
  _RepoRow('AtlasOfLivingAustralia', 'alerts',
      'User alert/notification service'),
  _RepoRow('AtlasOfLivingAustralia', 'data-quality-filter-service',
      'Data quality assertion and filtering'),
  _RepoRow('AtlasOfLivingAustralia', 'logger-service',
      'Download/usage event logging'),
  _RepoRow('AtlasOfLivingAustralia', 'doi-service',
      'DOI minting service for datasets'),
  _RepoRow('AtlasOfLivingAustralia', 'ala-hub',
      'Occurrence search web application'),
  _RepoRow('AtlasOfLivingAustralia', 'ala-namematching-service',
      'Taxon name matching microservice'),
  _RepoRow('AtlasOfLivingAustralia', 'sensitive-data-service',
      'Sensitive species data generalisation'),
  _RepoRow('living-atlases', 'generator-living-atlas',
      'Yeoman generator for LA node configuration'),
  _RepoRow('living-atlases', 'la-pipelines',
      'LA-specific GBIF pipelines extensions'),
  _RepoRow('living-atlases', 'la-streams',
      'Real-time streaming data pipeline (LA)'),
  _RepoRow('gbif', 'gbif-configuration',
      'GBIF production ansible/config reference'),
  _RepoRow('gbif', 'registry',
      'GBIF registry service (datasets, organisations)'),
  _RepoRow('gbif', 'checklistbank',
      'Checklist Bank — taxonomic data store'),
  _RepoRow('gbif', 'occurrence',
      'GBIF occurrence store and API'),
  _RepoRow('gbif', 'maps',
      'GBIF map tile service'),
  _RepoRow('gbif', 'geocode',
      'Reverse geocoding for occurrence data'),
];

class _RepoTable extends StatelessWidget {
  final List<_RepoRow> repos;

  const _RepoTable({required this.repos});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
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
                  _tdLink(context, r.repo, r.url),
                  _td(context, r.description),
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
              'repos_tier2.yml in the living-atlas-kb repo. Each entry needs:',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 12),
            _CodeBlock('''
- org: AtlasOfLivingAustralia
  repo: my-service
  description: Short description of the service
  branch: master          # optional, defaults to main
  paths:                  # optional glob filters
    - "**/*.yml"
    - "**/*.md"'''),
            const SizedBox(height: 12),
            Text(
              'Tier 1 repos are indexed daily. Tier 2 repos are indexed weekly.',
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
          method: 'GET',
          path: '/api/query',
          description: 'Semantic search. Params: q, collection, n_results',
          example: 'GET /api/query?q=how+to+configure+collectory&n_results=5',
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
