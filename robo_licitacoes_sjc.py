import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta
import requests

# ==============================================================================
# 1. CONFIGURAÇÕES DE ENDEREÇOS E APIs
# ==============================================================================
URL_PNCP = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
UF_SP = "SP"

URL_PLANILHA_TM = "https://script.google.com/macros/s/AKfycbxBhdjr_mhGsfNhLyT3Trx6aQZgjkoRsMCfeZK01HMTn85Gg5qAsK_Kfzcl_FT0a03f/exec"
TELEGRAM_TOKEN = "8269224927:AAHb26HEwbFWBeRtQpkOFHGVZLrEYlbuW4s"
TELEGRAM_CHAT_ID = "7193404104"

# 32 Cidades Mapeadas (Nomes Normalizados para Validação)
CIDADES_ALVO = [
    "SAO PAULO",
    "SAO JOSE DOS CAMPOS",
    "SANTOS",
    "JACAREI",
    "CACAPAVA",
    "TAUBATE",
    "PINDAMONHANGABA",
    "GUARATINGUETA",
    "LORENA",
    "CRUZEIRO",
    "SANTA BRANCA",
    "IGARATA",
    "PARAIBUNA",
    "UBATUBA",
    "CARAGUATATUBA",
    "SAO SEBASTIAO",
    "GUARULHOS",
    "ARUJA",
    "SANTA ISABEL",
    "MOGI DAS CRUZES",
    "SUZANO",
    "ITAQUAQUECETUBA",
    "POA",
    "FERRAZ DE VASCONCELOS",
    "CARAPICUIBA",
    "OSASCO",
    "SANTO ANDRE",
    "SAO BERNARDO DO CAMPO",
    "SAO CAETANO DO SUL",
    "DIADEMA",
    "MAUA",
    "RIBEIRAO PIRES",
]

TERMOS_PERMITIDOS = [
    r"\bPGR\b",
    r"\bLTCAT\b",
    r"\bPCMSO\b",
    r"\bSEGURANCA DO TRABALHO\b",
    r"\bLAUDO DE INSALUBRIDADE\b",
    r"\bLAUDO DE PERICULOSIDADE\b",
    r"\bANALISE ERGONOMICA\b",
    r"\bAET\b",
    r"\bLAUDO\b",
    r"\bLAUDOS\b",
    r"\bNR-10\b",
    r"\bNR10\b",
    r"\bNR-12\b",
    r"\bNR12\b",
    r"\bNR-13\b",
    r"\bNR13\b",
    r"\bNR-33\b",
    r"\bNR33\b",
    r"\bNR-35\b",
    r"\bNR35\b",
    r"\bTREINAMENTO NR\b",
    r"\bBRIGADA DE INCENDIO\b",
    r"\bPMOC\b",
    r"\bAR CONDICIONADO\b",
    r"\bADEQUACAO DE MAQUINAS\b",
    r"\bCALDEIRA\b",
    r"\bVASO DE PRESSAO\b",
    r"\bENGENHARIA MECANICA\b",
    r"\bSISTEMA DE EXAUSTAO\b",
    r"\bMANUTENCAO\b",
    r"\bAVCB\b",
    r"\bCLCB\b",
    r"\bCOMBATE A INCENDIO\b",
    r"\bCORPO DE BOMBEIROS\b",
    r"\bLAUDO TECNICO DE ENGENHARIA\b",
    r"\bPERICIA\b",
    r"\bVISTORIA\b",
    r"\bINSPECAO\b",
    r"\bCARREGADOR ELETRICO\b",
    r"\bPONTO DE RECARGA\b",
    r"\bESTACAO DE RECARGA\b",
    r"\bIT 43\b",
    r"\bIT-43\b",
    r"\bCARRO ELETRICO\b",
    r"\bVEICULO ELETRICO\b",
    r"\bELETROPOSTO\b",
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


def validar_cidade_alvo(municipio_nome: str) -> bool:
  nome_limpo = remover_acentos(municipio_nome)
  return any(cidade in nome_limpo for cidade in CIDADES_ALVO)


def validar_objeto_licitacao(objeto_texto: str) -> bool:
  texto_tratado = remover_acentos(objeto_texto)
  if any(
      re.search(re.compile(termo, re.IGNORECASE), texto_tratado)
      for termo in TERMOS_PROIBIDOS
  ):
    return False
  if any(
      re.search(re.compile(termo, re.IGNORECASE), texto_tratado)
      for termo in TERMOS_PERMITIDOS
  ):
    return True
  return False


def enviar_oportunidade_para_planilha(
    orgao, valor_estimado, objeto, link_edital=""
):
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
  print("🚀 INICIANDO MONITORAMENTO - TM ENGENHARIA CONSULTORIA")
  print("==================================================================")

  data_fim = datetime.now()
  data_ini = data_fim - timedelta(days=90)

  data_inicial_str = data_ini.strftime("%Y%m%d")
  data_final_str = data_fim.strftime("%Y%m%d")

  total_varridas = 0
  total_oportunidades_tm = 0
  lista_json_vercel = []

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
      "Accept": "application/json",
  }

  modalidades = [6, 8, 14]

  for mod in modalidades:
    print(f"🔍 Consultando Modalidade PNCP: {mod}...")

    for pagina in range(1, 15):  # Busca profunda de páginas
      params = {
          "dataInicial": data_inicial_str,
          "dataFinal": data_final_str,
          "codigoModalidadeContratacao": mod,
          "uf": UF_SP,
          "pagina": pagina,
          "tamPag": 50,
      }
      try:
        resposta = requests.get(
            URL_PNCP, params=params, headers=headers, timeout=15
        )
        if resposta.status_code != 200:
          break
        dados_pagina = resposta.json()
      except Exception:
        break

      lista_editais = dados_pagina.get("data") or []
      if not lista_editais:
        break

      total_varridas += len(lista_editais)

      for edital in lista_editais:
        objeto_descricao = (
            edital.get("objetoCompra")
            or edital.get("objetoContratacao")
            or edital.get("objeto")
            or ""
        )
        municipio_nome = (
            edital.get("unidadeOrgao", {}).get("municipioNome") or ""
        )

        # VALIDAÇÃO DUPLA: Objeto de Engenharia/SST + Pertencer às 32 Cidades
        if validar_objeto_licitacao(
            objeto_descricao
        ) and validar_cidade_alvo(municipio_nome):
          total_oportunidades_tm += 1
          orgao_nome = edital.get("orgaoEntidade", {}).get(
              "razaoSocial", "Órgão Omitido"
          )
          valor_estimado = edital.get("valorTotalEstimado") or 0.0

          cnpj_orgao = re.sub(
              r"\D", "", str(edital.get("orgaoEntidade", {}).get("cnpj", ""))
          )
          ano_contrato = edital.get("anoContratacao")
          seq_contrato = edital.get("sequencialContratacao")

          if cnpj_orgao and ano_contrato and seq_contrato:
            link_painel_pncp = f"https://pncp.gov.br/app/editais/{cnpj_orgao}/{ano_contrato}/{seq_contrato}"
          else:
            link_painel_pncp = "https://pncp.gov.br/app/editais"

          print(
              f"    🎯 FOCADO ({municipio_nome}): {orgao_nome[:30]} | R$"
              f" {valor_estimado:,.2f}"
          )

          lista_json_vercel.append({
              "orgao": orgao_nome,
              "cidade": municipio_nome,
              "valor": valor_estimado,
              "objeto": objeto_descricao,
              "link": link_painel_pncp,
              "data_captura": datetime.now().strftime("%d/%m/%Y %H:%M"),
          })

          enviar_oportunidade_para_planilha(
              orgao_nome, valor_estimado, objeto_descricao, link_painel_pncp
          )

          msg_telegram = (
              f"🎯 *NOVA OPORTUNIDADE REGIONAL FILTRADA!*\n\n"
              f"🏢 *Órgão:* {orgao_nome}\n"
              f"📍 *Cidade:* {municipio_nome}\n"
              f"💰 *Valor Estimado:* R$ {valor_estimado:,.2f}\n"
              f"📋 *Objeto:* {objeto_descricao[:180]}...\n\n"
              f"🔗 [Abrir Painel Oficial do Edital]({link_painel_pncp})"
          )
          enviar_alerta_telegram(msg_telegram)

      time.sleep(0.3)

  with open("licitacoes.json", "w", encoding="utf-8") as f:
    json.dump(lista_json_vercel, f, ensure_ascii=False, indent=2)

  print("\n==================================================================")
  print(
      f"📋 FIM DA VARREDURA! Analisados: {total_varridas} | Injetados Na"
      f" Região: {total_oportunidades_tm}"
  )
  print("==================================================================")


if __name__ == "__main__":
  executar_mapeamento_pncp()
