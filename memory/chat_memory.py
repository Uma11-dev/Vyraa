"""
Conversation Memory Manager

This module is responsible for storing and retrieving
conversation history for each chat session.

Version 1:
------------
Stores conversation history in memory using a Python dictionary.

Future Versions:
----------------
- Redis
- PostgreSQL
- LangGraph Checkpointer
"""

from langchain_core.messages import HumanMessage, AIMessage


class ChatMemory:

    def __init__(self):
        """
        Dictionary format

        {
            session_id: [
                HumanMessage(...),
                AIMessage(...),
                ...
            ]
        }
        """

        self.memory_store = {}

    # ---------------------------------------------

    def load_history(self, session_id: str,collection_name:str):
        """
        Load conversation history.

        Parameters
        ----------
        session_id : str

        Returns
        -------
        list
            List of LangChain messages.
        """

        return self.memory_store.get(session_id, [])

    # ---------------------------------------------

    def save_user_message(self, session_id: str, message: str,collection_name:str):

        if session_id not in self.memory_store:
            self.memory_store[session_id] = []

        self.memory_store[session_id].append(
            HumanMessage(content=message)
        )

    # ---------------------------------------------

    def save_ai_message(self, session_id: str, message: str,collection_name:str):

        if session_id not in self.memory_store:
            self.memory_store[session_id] = []

        self.memory_store[session_id].append(
            AIMessage(content=message)
        )

    # ---------------------------------------------

    def clear_memory(self, session_id: str):

        self.memory_store.pop(session_id, None)



chat_memory = ChatMemory()