"""Linha de comando: python -m evasao baixar|processar|consolidar|api|auditoria."""

import argparse
import logging
import sys

from evasao.config import ANOS


def ler_anos(texto):
    """Aceita "2023", "2009-2024" ou "2019,2021-2023"."""
    anos = set()
    for parte in texto.split(","):
        inicio, _, fim = parte.strip().partition("-")
        anos.update(range(int(inicio), int(fim or inicio) + 1))
    return sorted(anos)


def main():
    # o terminal do Windows usa cp1252 e quebra com alguns nomes de arquivo dos ZIPs
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(prog="python -m evasao")
    comandos = ["baixar", "processar", "consolidar", "api", "auditoria"]
    parser.add_argument("comando", choices=comandos)
    parser.add_argument("--anos", type=ler_anos, default=list(ANOS), help="ex.: 2009-2024")
    parser.add_argument("--forcar", action="store_true", help="baixa/processa de novo")
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()

    erros = []
    if args.comando == "baixar":
        from evasao.coleta import baixar_ano

        for ano in args.anos:
            try:
                baixar_ano(ano, forcar=args.forcar)
            except Exception as e:
                erros.append(f"{ano}: {e}")

    elif args.comando == "processar":
        from evasao.processamento import processar_ano

        for ano in args.anos:
            try:
                processar_ano(ano, forcar=args.forcar)
            except Exception as e:  # um ano com problema não impede os outros
                logging.exception("erro no ano %s", ano)
                erros.append(f"{ano}: {e}")

    elif args.comando == "consolidar":
        from evasao.consolidacao import consolidar

        consolidar()

    elif args.comando == "auditoria":
        from evasao.consolidacao import auditoria

        for arquivo in auditoria():
            print("gerado:", arquivo)

    elif args.comando == "api":
        import uvicorn

        print(f"site e API em http://127.0.0.1:{args.porta}/  (docs em /docs)")
        uvicorn.run("evasao.api:app", host="127.0.0.1", port=args.porta)

    if erros:
        print("Anos com erro:\n" + "\n".join(erros), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
