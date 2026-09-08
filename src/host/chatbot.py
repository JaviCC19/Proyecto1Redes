#!/usr/bin/env python3


from __future__ import annotations

import json
import os
import sys

from env_loader import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

import ui
from context import SessionContext
from llm_client import AnthropicClient, LLMError
from logger import InteractionLogger
from mcp_manager import MCPManager

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace")   # sandbox for the Filesystem server
GIT_REPO_DIR = os.path.join(PROJECT_ROOT, "workspace_git")  # sandbox repo for the Git server
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

SYSTEM_PROMPT = """Eres un asistente conversacional (chatbot) construido para el Proyecto 1 de
CC3067 Redes (UVG). Puedes responder preguntas generales, y además tienes acceso a herramientas
(tools) expuestas por distintos servidores MCP:

- Herramientas con prefijo "fs__": operan sobre el sistema de archivos local (servidor oficial
  Filesystem MCP), dentro de un directorio de trabajo controlado.
- Herramientas con prefijo "git__": operan sobre un repositorio git local (servidor oficial Git
  MCP).
- Herramientas con prefijo "offers__": tu propio servidor MCP de recomendación de ofertas/
  promociones (caso de uso de industria: retail/e-commerce). Úsalo cuando el usuario pregunte por
  descuentos, promociones u ofertas. Primero hazle un par de preguntas cortas sobre sus intereses,
  presupuesto o categoría preferida antes de llamar a "offers__match_offers".

Usa las herramientas solo cuando realmente ayuden a responder lo que el usuario pide. Sé claro y
conciso en español, a menos que el usuario te hable en otro idioma."""


def extract_text(content_blocks: list[dict]) -> str:
    parts = []
    for block in content_blocks:
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts)


def run_agent_turn(llm: AnthropicClient, session: SessionContext, mcp_manager: MCPManager) -> str:
    """Runs the Anthropic tool-use loop for the *current* last user
    message already stored in `session`, handling as many tool_use /
    tool_result round-trips as the model requests, and returns the
    final assistant text to show the user."""
    tools = mcp_manager.all_tools_for_llm()

    while True:
        with ui.Spinner("Pensando"):
            response = llm.create_message(
                messages=session.as_api_messages(),
                system=SYSTEM_PROMPT,
                tools=tools,
            )
        content = response.get("content", [])
        stop_reason = response.get("stop_reason")

        session.add_assistant_message(content)

        if stop_reason != "tool_use":
            return extract_text(content)

        tool_results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            tool_name = block["name"]
            tool_input = block.get("input", {})
            tool_use_id = block["id"]
            alias, _, bare_name = tool_name.partition("__")
            print(ui.tool_call_line(alias, bare_name or tool_name, tool_input))
            try:
                mcp_result = mcp_manager.call_tool(tool_name, tool_input)
                result_text = json.dumps(mcp_result, ensure_ascii=False)
                is_error = bool(mcp_result.get("isError"))
            except Exception as exc:  # noqa: BLE001
                result_text = f"Error invocando la herramienta {tool_name}: {exc}"
                is_error = True

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_text,
                "is_error": is_error,
            })

        session.add_user_message(tool_results)


def main() -> None:
    logger = InteractionLogger(log_dir=LOGS_DIR)

    try:
        llm = AnthropicClient()
    except LLMError as exc:
        print(ui.error(str(exc)), file=sys.stderr)
        sys.exit(1)

    mcp_manager = MCPManager(logger=logger, workspace_dir=WORKSPACE_DIR, git_repo_dir=GIT_REPO_DIR)
    print(ui.system("Iniciando servidores MCP (filesystem, git, offers)..."), file=sys.stderr)
    mcp_manager.start_all()
    tool_count = len(mcp_manager.all_tools_for_llm())
    print(ui.success(f"{tool_count} herramientas disponibles.\n"), file=sys.stderr)

    session = SessionContext(persist_dir=os.path.join(LOGS_DIR, "sessions"))

    print(ui.banner("Chatbot CC3067 - Proyecto 1", "escribe 'salir' para terminar"))
    print()
    try:
        while True:
            try:
                user_input = input(ui.user_prompt()).strip()
            except EOFError:
                break
            if not user_input:
                continue
            if user_input.lower() in {"salir", "exit", "quit"}:
                break

            session.add_user_message(user_input)
            try:
                reply = run_agent_turn(llm, session, mcp_manager)
            except LLMError as exc:
                print(ui.error(str(exc)))
                continue
            print(f"{ui.bot_label()}{reply}\n")
    finally:
        mcp_manager.close_all()


if __name__ == "__main__":
    main()
