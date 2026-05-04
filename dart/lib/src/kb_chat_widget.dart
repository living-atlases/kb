import 'package:flutter/foundation.dart';
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
    _client.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _handleSend(ChatMessage userMessage) async {
    // Add user message immediately
    _controller.addMessage(userMessage);
    setState(() => _isLoading = true);

    // Create a placeholder bot message that we'll update token by token
    // Use a stable custom ID so updateMessage can find it after copyWith
    final botMsgId = 'bot_${DateTime.now().millisecondsSinceEpoch}';
    final botMsg = ChatMessage(
      text: '',
      user: _userBot,
      createdAt: DateTime.now(),
      isMarkdown: true,
      customProperties: {'id': botMsgId},
    );
    _controller.addMessage(botMsg);
    debugPrint('BOT MSG ID: $botMsgId — messages count: ${_controller.messages.length}');

    final buffer = StringBuffer();

    try {
      await for (final token in _client.chat(userMessage.text)) {
        buffer.write(token);
        final beforeCount = _controller.messages.length;
        _controller.updateMessage(
          botMsg.copyWith(
            text: buffer.toString(),
            customProperties: {'id': botMsgId},
          ),
        );
        final afterCount = _controller.messages.length;
        if (afterCount != beforeCount) {
          debugPrint('DUPLICATE ADDED! before=$beforeCount after=$afterCount botMsgId=$botMsgId');
          // Check actual IDs in controller
          for (final m in _controller.messages) {
            debugPrint('  msg id=${m.customProperties?['id']} user=${m.user.id} text=${m.text.length}chars');
          }
        }
      }
    } on KbException catch (e) {
      _controller.updateMessage(
        botMsg.copyWith(
          text: '_Error: ${e.message}_',
          customProperties: {'id': botMsgId},
        ),
      );
    } catch (e) {
      _controller.updateMessage(
        botMsg.copyWith(
          text: '_Unexpected error: ${e}_',
          customProperties: {'id': botMsgId},
        ),
      );
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AiChatWidget(
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
    );
  }
}
