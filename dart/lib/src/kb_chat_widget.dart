import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_gen_ai_chat_ui/flutter_gen_ai_chat_ui.dart';

import 'kb_client.dart';
import 'kb_config.dart';

/// Starter questions shown in the empty chat state.
const _kStarterQuestions = [
  'How do I install collectory?',
  'How do I configure biocache-service?',
  'What does ala-install configure for spatial-hub?',
  'How do I set up the image service?',
  'What Ansible roles are needed for a basic LA deployment?',
];

/// Maximum number of prior messages (user+assistant) sent as history.
const int _kMaxHistoryMessages = 12;

/// Ready-to-use chat widget that connects to the Living Atlas KB.
///
/// Displays a full-screen chat UI powered by [flutter_gen_ai_chat_ui].
/// Streams answers from the KB `/api/chat` endpoint via SSE.
///
/// Example:
/// ```dart
/// KbChatWidget(config: KbConfig(baseUrl: 'https://kb.l-a.site'))
/// ```
class KbChatWidget extends StatefulWidget {
  final KbConfig config;

  /// Optional custom title for the app bar / header.
  final String title;

  const KbChatWidget({
    super.key,
    required this.config,
    this.title = 'Living Atlas KB',
  });

  @override
  State<KbChatWidget> createState() => _KbChatWidgetState();
}

class _KbChatWidgetState extends State<KbChatWidget> {
  late final KbClient _client;
  late final ChatMessagesController _controller;
  late final ChatUser _userMe;
  late final ChatUser _userBot;
  bool _isLoading = false;
  StreamSubscription<String>? _streamSub;

  @override
  void initState() {
    super.initState();
    _client = KbClient(config: widget.config);
    _userMe = const ChatUser(id: 'user', name: 'You');
    _userBot = const ChatUser(id: 'bot', name: 'LA Knowledge Base');
    _controller = ChatMessagesController();
  }

  @override
  void dispose() {
    _streamSub?.cancel();
    _client.dispose();
    _controller.dispose();
    super.dispose();
  }

  /// Build conversation history from messages already in the controller.
  ///
  /// Excludes the user message just added (current turn). Keeps only the
  /// last [_kMaxHistoryMessages] entries to bound prompt size.
  List<Map<String, String>> _buildHistory(ChatMessage currentUserMessage) {
    final history = <Map<String, String>>[];
    for (final m in _controller.messages) {
      if (identical(m, currentUserMessage)) continue;
      if (m.user.id == _userMe.id) {
        history.add({'role': 'user', 'content': m.text});
      } else if (m.user.id == _userBot.id) {
        if (m.text.trim().isEmpty) continue;
        history.add({'role': 'assistant', 'content': m.text});
      }
    }
    if (history.length > _kMaxHistoryMessages) {
      return history.sublist(history.length - _kMaxHistoryMessages);
    }
    return history;
  }

  Future<void> _handleSend(ChatMessage userMessage) async {
    _controller.addMessage(userMessage);

    // Snapshot history BEFORE adding the placeholder bot message.
    final history = _buildHistory(userMessage);

    setState(() => _isLoading = true);

    final botMsgId = 'bot_${DateTime.now().millisecondsSinceEpoch}';
    final botMsg = ChatMessage(
      text: '',
      user: _userBot,
      createdAt: DateTime.now(),
      isMarkdown: true,
      customProperties: {'id': botMsgId},
    );
    _controller.addStreamingMessage(botMsg);

    final buffer = StringBuffer();
    final completer = Completer<void>();

    void updateBot(String text) {
      _controller.updateMessage(botMsg.copyWith(text: text));
    }

    _streamSub = _client.chat(userMessage.text, history: history).listen(
      (token) {
        buffer.write(token);
        updateBot(buffer.toString());
      },
      onError: (e) {
        if (e is KbException) {
          updateBot('_Error: ${e.message}_');
        } else {
          updateBot('_Unexpected error: ${e}_');
        }
        if (!completer.isCompleted) completer.complete();
      },
      onDone: () {
        if (!completer.isCompleted) completer.complete();
      },
      cancelOnError: true,
    );

    try {
      await completer.future;
    } finally {
      _streamSub = null;
      _controller.stopStreamingMessage(botMsgId);
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _handleStop() {
    final sub = _streamSub;
    if (sub == null) return;
    sub.cancel();
    _streamSub = null;
    // Append "(stopped)" marker to the most recent bot message.
    for (final m in _controller.messages.reversed) {
      if (m.user.id == _userBot.id) {
        _controller.updateMessage(
          m.copyWith(text: '${m.text}\n\n_(stopped)_'),
        );
        final stoppedId = m.customProperties?['id'] as String?;
        if (stoppedId != null) {
          _controller.stopStreamingMessage(stoppedId);
        }
        break;
      }
    }
    if (mounted) setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        AiChatWidget(
          currentUser: _userMe,
          aiUser: _userBot,
          controller: _controller,
          onSendMessage: _handleSend,
          loadingConfig: LoadingConfig(isLoading: _isLoading),
          aiName: widget.title,
          enableAnimation: true,
          exampleQuestions: _kStarterQuestions
              .map((q) => ExampleQuestion(question: q))
              .toList(),
          inputOptions: const InputOptions(
            decoration: InputDecoration(
              hintText: 'Ask about LA services, ala-install, biocache…',
            ),
          ),
          messageOptions: MessageOptions(
            showCopyButton: true,
            onCopy: (text) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Copied'),
                  duration: Duration(seconds: 1),
                ),
              );
            },
          ),
        ),
        if (_isLoading)
          Positioned(
            right: 16,
            bottom: 80,
            child: FloatingActionButton.small(
              heroTag: 'kb_stop_btn',
              tooltip: 'Stop',
              onPressed: _handleStop,
              child: const Icon(Icons.stop),
            ),
          ),
      ],
    );
  }
}
