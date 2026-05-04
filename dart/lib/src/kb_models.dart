/// Data models for Living Atlas KB API responses.

class QueryResult {
  final String content;
  final Map<String, dynamic> metadata;
  final double relevance;

  const QueryResult({
    required this.content,
    required this.metadata,
    required this.relevance,
  });

  factory QueryResult.fromJson(Map<String, dynamic> json) => QueryResult(
        content: json['content'] as String,
        metadata: Map<String, dynamic>.from(json['metadata'] as Map),
        relevance: (json['relevance'] as num).toDouble(),
      );
}

class QueryResponse {
  final List<QueryResult> results;

  const QueryResponse({required this.results});

  factory QueryResponse.fromJson(Map<String, dynamic> json) => QueryResponse(
        results: (json['results'] as List)
            .map((e) => QueryResult.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class CollectionInfo {
  final String name;
  final int count;

  const CollectionInfo({required this.name, required this.count});

  factory CollectionInfo.fromJson(Map<String, dynamic> json) => CollectionInfo(
        name: json['name'] as String,
        count: json['count'] as int,
      );
}
