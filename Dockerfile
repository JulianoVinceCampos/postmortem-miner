# Imagem do dashboard. Enxuta por consequencia, nao por esforco: o pacote tem zero
# dependencia de runtime (ADR-0001), entao nao existe resolucao de dependencia aqui.
# Sem lock file para divergir, sem indice para alcancar, sem cache de wheel.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PM_USER=demo \
    PM_PASSWORD=demo

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && adduser --system --no-create-home --uid 10001 miner

# O corpus e dado, nao codigo. Monte o seu acervo sobre /app/corpus para analisar de
# verdade; o sintetico viaja na imagem so para o demo ter o que mostrar.
COPY corpus ./corpus

USER 10001

EXPOSE 8000

# Le PORT porque plataforma de deploy injeta a porta. Sem PORT, cai em 8000.
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
    CMD python -c "import os,sys,urllib.request; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/api/health',timeout=3).status==200 else 1)"

# 0.0.0.0 dentro do container e deliberado: o processo so ve o namespace de rede do
# container, e o default de loopback da CLI o deixaria inalcancavel. A porta fica de
# fora do comando de proposito, para o default ler PORT do ambiente.
CMD ["postmortem-miner", "serve", "corpus", "--host", "0.0.0.0"]
