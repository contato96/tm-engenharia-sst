import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta
import requests

# ==============================================================================
# 1. CONFIGURAÇÕES E PARÂMETROS DE BUSCA
# ==============================================================================
URL_PNCP_BUSCA = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
UF_SP = "SP"

URL_PLANILHA_TM = "https://script.google.com/macros/s/AKfycbxBhdjr_mhGsfNhLyT3Trx6aQZgjkoRsMCfeZK01HMTn85Gg5qAsK_Kfzcl_FT0a03f/exec"
TELEGRAM_TOKEN = "8269224927:AAHb26HEwbFWBeRtQpkOFHGVZLrEYlbuW4s"
TELEGRAM_CHAT_ID = "7193404104"

# Palavras-chave para consulta direta na API do PNCP
TERMOS_BUSCA_API = [
    "PGR",
    "LTCAT",
    "PCMSO",
    "SEGURANCA DO TRABALHO",
    "LAUDO DE INSALUBRIDADE",
    "LAUDO DE PERICULOSIDADE",
    "ANALISE ERGONOMICA",
    "NR-10",
    "NR-12",
    "NR-13",
    "NR-33",
    "NR-35",
    "BRIGADA DE INCENDIO",
    "PMOC",
    "AVCB",
    "ENGENHARIA MECANICA",
    "VISTORIA ENGENHARIA",
]

TERMOS_PROIBIDOS = [
    r"PISCINA",
    r"LIMPEZA",
    r"ZELADORIA",
    r"JARDINAGEM",
    r"REFEICAO",
    r"ALIMENTACAO",
    r"UNIFORME",
    r"VIGILANCIA",
    r"SEGURANCA ARMADA",
    r"TRANSPORTE ESCOLAR",
    r"LOCACAO DE VEICULO",
]


def remover_acentos(texto: str) -> str:
  if not texto:
    return ""
  nfkd = unicodedata.normalize("NFKD", str(texto))
  return "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()


def validar_objeto_licitacao(objeto_texto: str) -> bool:
  texto_tratado = remover_acentos(objeto_texto)
  if any(
      re.search(re.compile(termo, re.IGNORECASE), texto_tratado)
      for termo in TERMOS_PROIBIDOS
  ):
    return False
  return True


def enviar_oportunidade_para_planilha(orgao, valor_estimado, objeto):
  params = {
      "tipo": "sheet",
      "orgao": orgao,
      "valor": str(valor_estimado),
      "objeto": objeto,
      "escopo": objeto,
  }
  try:
    requests.get(URL_PLANILHA_TM, params=params, timeout=10)
  except Exception:
    pass


def enviar_alerta_telegram(mensagem: str):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  try:
    requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensagem,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )
  except Exception:
    pass


def executar_mapeamento_pncp():
  print("==================================================================")
  print("🚀 INICIANDO MONITORAMENTO DE ENGENHARIA & SST - PNCP")
  print("==================================================================")

  data_fim = datetime.now()
  data_ini = data_fim - timedelta(days=90)

  data_inicial_str = data_ini.strftime("%Y%m%d")
  data_final_str = data_fim.strftime("%Y%m%d")

  total_varridas = 0
  total_oportunidades_tm = 0
  licitacoes_encontradas = []
  ids_processados = set()

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      )
  }

  for termo in TERMOS_BUSCA_API:
    print(f"🔍 Consultando PNCP por termo: '{termo}'...")
    pagina = 1

    while pagina <= 2:
      params = {
          "dataInicial": data_inicial_str,
          "dataFinal": data_final_str,
          "uf": UF_SP,
          "q": termo,
          "pagina": pagina,
          "tamPag": 50,
      }
      try:
        resposta = requests.get(
            URL_PNCP_BUSCA, params=params, headers=headers, timeout=15
        )
        if resposta.status_code != 200:
          break
        dados = resposta.json()
      except Exception:
        break

      items = (
          dados.get("data")
          or dados.get("resultados")
          or (dados if isinstance(dados, list) else [])
      )
      if not items:
        break

      total_varridas += len(items)

      for edital in items:
        cnpj_orgao = re.sub(
            r"\D", "", str(edital.get("orgaoEntidade", {}).get("cnpj", ""))
        )
        ano_contrato = edital.get("anoContratacao") or edital.get("ano")
        seq_contrato = edital.get("sequencialContratacao") or edital.get(
            "sequencial"
        )
        edital_id = f"{cnpj_orgao}_{ano_contrato}_{seq_contrato}"

        if edital_id in ids_processados:
          continue
        ids_processados.add(edital_id)

        objeto_descricao = (
            edital.get("objetoCompra")
            or edital.get("objetoContratacao")
            or edital.get("objeto")
            or ""
        )

        if validar_objeto_licitacao(objeto_descricao):
          total_oportunidades_tm += 1
          orgao_nome = (
              edital.get("orgaoEntidade", {}).get("razaoSocial")
              or edital.get("orgaoRazaoSocial")
              or "Órgão Público - SP"
          )
          municipio_nome = (
              edital.get("unidadeOrgao", {}).get("municipioNome") or "SP"
          )
          valor_estimado = edital.get("valorTotalEstimado") or 0.0

          if cnpj_orgao and ano_contrato and seq_contrato:
            link_painel_pncp = f"https://pncp.gov.br/app/editais/{cnpj_orgao}/{ano_contrato}/{seq_contrato}"
          else:
            link_painel_pncp = "https://pncp.gov.br/app/editais"

          print(f"   🎯 FOCADO: {orgao_nome[:35]} | R$ {valor_estimado:,.2f}")

          licitacoes_encontradas.append({
              "orgao": orgao_nome,
              "cidade": municipio_nome,
              "valor": valor_estimado,
              "objeto": objeto_descricao,
              "link": link_painel_pncp,
              "data_captura": datetime.now().strftime("%d/%m/%Y %H:%M"),
          })

          enviar_oportunidade_para_planilha(
              orgao_nome, valor_estimado, objeto_descricao
          )

          msg_telegram = (
              f"🎯 *NOVA OPORTUNIDADE FILTRADA!*\n\n"
              f"🏢 *Órgão:* {orgao_nome}\n"
              f"📍 *Cidade:* {municipio_nome}\n"
              f"💰 *Valor Estimado:* R$ {valor_estimado:,.2f}\n"
              f"📋 *Objeto:* {objeto_descricao[:180]}...\n\n"
              f"🔗 [Abrir Painel Oficial do Edital]({link_painel_pncp})"
          )
          enviar_alerta_telegram(msg_telegram)

      pagina += 1
      time.sleep(0.2)

  # Salva arquivo para a Vercel
  with open("licitacoes.json", "w", encoding="utf-8") as f:
    json.dump(licitacoes_encontradas, f, ensure_ascii=False, indent=2)

  print("\n==================================================================")
  print(
      f"📋 FIM DA VARREDURA! Analisados: {total_varridas} | Injetados:"
      f" {total_oportunidades_tm}"
  )
  print("==================================================================")


if __name__ == "__main__":
  executar_mapeamento_pncp()
