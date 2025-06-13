# dev-group_supervisor

Utilities for automating routine tasks around development. The
`chat_history_compressor.py` module provides a `ChatHistoryCompressor`
class which uses the DeepSeek Reasoner API to recursively compress a
long OpenAI chat history. It keeps important dates and numbers intact
while summarising each block until the history fits within two thirds
of the target model token limit.
