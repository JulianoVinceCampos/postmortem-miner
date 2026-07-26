#!/usr/bin/env python3
"""Generate a synthetic postmortem corpus.

Every incident here is fabricated. Service names, hosts and addresses are placeholders
(RFC 5737 ranges), and no real system, customer or colleague appears. The *shapes* are
realistic because they are drawn from failure modes that are common to any JVM +
relational-database stack behind a load balancer - which is exactly what makes the
corpus useful for testing a pattern miner.

Deterministic: same seed, same corpus, byte for byte. The README numbers depend on it.

    python3 tools/gen_corpus.py --out corpus --count 18 --seed 7
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SERVICES = ("svc-ledger", "svc-billing", "svc-intake", "svc-notify", "svc-registry")
SEVERITIES = ("P1", "P1", "P2")
# Half the corpus is written in Portuguese: the extractor claims to be bilingual, so
# the fixture that exercises it has to be too.
_PT_RATIO = 0.5
# Members of a family drop at most one signal, and only when there is one to spare.
_DROP_CHANCE = 0.5
_MIN_SIGNALS_TO_DROP = 3


@dataclass(frozen=True, slots=True)
class Family:
    key: str
    title_en: str
    title_pt: str
    signals_en: tuple[str, ...]
    signals_pt: tuple[str, ...]
    trigger_en: str
    trigger_pt: str
    mitigation_en: str
    mitigation_pt: str
    root_cause_open: bool


FAMILIES: tuple[Family, ...] = (
    Family(
        key="pool-lock",
        title_en="Connection pool exhaustion with database lock contention",
        title_pt="Esgotamento do pool de conexoes com contencao de locks no banco",
        signals_en=(
            "Database CPU climbed to {cpu}% and stayed there for {mins} minutes.",
            "The JDBC pool sat at {pool}/{pool} with WaitCount above zero on every node.",
            "The DBA found sessions holding locks on the main write table.",
            "All nodes showed the same CPU profile, so this was not isolated to one host.",
        ),
        signals_pt=(
            "CPU do banco subiu para {cpu}% e ficou nesse patamar por {mins} minutos.",
            "Pool JDBC em {pool}/{pool} com WaitCount acima de zero em todos os nos.",
            "O DBA identificou sessoes em lock na tabela principal de escrita.",
            "Todos os nos apresentaram o mesmo perfil de CPU - nao ficou isolado em um no.",
        ),
        trigger_en="A cascading ORM flush turned one business operation into dozens of statements.",
        trigger_pt="Um flush em cascata do ORM transformou uma operacao em dezenas de statements.",
        mitigation_en="Sequential restart of the application nodes plus the DBA killing locked sessions.",
        mitigation_pt="Restart sequencial dos nos da aplicacao e o DBA encerrando sessoes em lock.",
        root_cause_open=True,
    ),
    Family(
        key="heap-oom",
        title_en="Heap exhaustion while handling an oversized payload",
        title_pt="Estouro de heap ao processar payload muito grande",
        signals_en=(
            "Node {node} threw OOM at {hour}:17 while parsing a {mb} MB request.",
            "Full GC ran back to back and old gen stayed full.",
            "Only 1 node was affected; the rest of the fleet kept serving traffic.",
            "The inbound file carried {count} records in a single request.",
        ),
        signals_pt=(
            "O no {node} lancou OOM as {hour}:17 ao parsear uma requisicao de {mb} MB.",
            "Full GC rodou em sequencia e a old gen permaneceu cheia.",
            "Apenas 1 no foi afetado; o restante da frota seguiu atendendo.",
            "O arquivo de entrada trazia {count} registros numa unica requisicao.",
        ),
        trigger_en="The whole document is materialised in memory before persistence begins.",
        trigger_pt="O documento inteiro e materializado em memoria antes de iniciar a persistencia.",
        mitigation_en="Restarted the affected process and asked the partner to split the batch.",
        mitigation_pt="Reiniciamos o processo afetado e pedimos ao parceiro para dividir a remessa.",
        root_cause_open=True,
    ),
    Family(
        key="retry-storm",
        title_en="Scheduled job retry loop turned into a thundering herd",
        title_pt="Loop de retry de job agendado virou thundering herd",
        signals_en=(
            "Database CPU stayed high for {mins} minutes while the batch host CPU was 2%.",
            "Logs showed a retry loop with no backoff across three scheduled timers.",
            "The nightly batch window overlapped with the first heavy query of the day.",
            "Thread pool on the batch node reached {threads} threads.",
        ),
        signals_pt=(
            "CPU do banco alta por {mins} minutos enquanto a CPU do host de batch ficou em 2%.",
            "Logs mostraram retry em loop sem backoff em tres timers agendados.",
            "A janela de batch noturno coincidiu com a primeira query pesada do dia.",
            "O thread pool do no de batch alcancou {threads} threads.",
        ),
        trigger_en="A transient database spike made every timer fail and immediately retry.",
        trigger_pt="Um spike transitorio no banco fez cada timer falhar e reintentar de imediato.",
        mitigation_en="Restarted the batch process only - no reboot - and staggered the schedule.",
        mitigation_pt="Reiniciamos apenas o processo de batch - sem reboot - e escalonamos o schedule.",
        root_cause_open=True,
    ),
    Family(
        key="rollback",
        title_en="Long rollback of a monolithic transaction",
        title_pt="Rollback longo de uma transacao monolitica",
        signals_en=(
            "The database looked busy with no new operations arriving - it was undoing work.",
            "A single huge transaction had been open for {mins} minutes before failing.",
            "Restarting did not help: crash recovery resumed the rollback.",
            "Undo log growth tracked the volume already written.",
        ),
        signals_pt=(
            "O banco parecia ocupado sem novas operacoes chegando - estava desfazendo trabalho.",
            "Uma transacao unica ficou aberta por {mins} minutos antes de falhar.",
            "Reiniciar nao ajudou: o crash recovery retomou o rollback.",
            "O crescimento do undo log acompanhou o volume ja escrito.",
        ),
        trigger_en="One request equals one transaction, so failure cost is proportional to volume.",
        trigger_pt="Uma requisicao equivale a uma transacao, e o custo da falha e proporcional ao volume.",
        mitigation_en="Freed CPU by ending waiting sessions and waited it out. Forcing a restart is worse.",
        mitigation_pt="Liberamos CPU encerrando sessoes em espera e aguardamos. Forcar restart e pior.",
        root_cause_open=True,
    ),
    Family(
        key="cert",
        title_en="Expired TLS certificate took the public endpoint down",
        title_pt="Certificado TLS expirado derrubou o endpoint publico",
        signals_en=(
            "The certificate on the edge listener had expired {days} days earlier.",
            "Health check failures started at the same minute for every target.",
            "Clients outside the VPN saw connection timed out; internal calls were fine.",
            "No deploy had happened in the previous week.",
        ),
        signals_pt=(
            "O certificado do listener de borda havia expirado {days} dias antes.",
            "Falhas de health check comecaram no mesmo minuto para todos os targets.",
            "Clientes fora da VPN viam connection timed out; chamadas internas seguiam ok.",
            "Nenhum deploy havia ocorrido na semana anterior.",
        ),
        trigger_en="Renewal was manual and the calendar reminder had no owner.",
        trigger_pt="A renovacao era manual e o lembrete no calendario nao tinha responsavel.",
        mitigation_en="Replaced the keystore and reloaded the listener. Root cause addressed: renewal automated.",
        mitigation_pt="Trocamos o keystore e recarregamos o listener. Causa raiz tratada: renovacao automatizada.",
        root_cause_open=False,
    ),
    Family(
        key="acl",
        title_en="External access blocked by a security group range gap",
        title_pt="Acesso externo bloqueado por lacuna de range no security group",
        signals_en=(
            "The app answered through the VPN but timed out from outside.",
            "Load balancer health check was failing from the subnet range {ip}0/24.",
            "The security group ingress rule did not cover the balancer subnets.",
            "No application error appeared in the logs at all.",
        ),
        signals_pt=(
            "A aplicacao respondia pela VPN mas dava timeout de fora da VPN.",
            "O health check do balanceador falhava a partir do range {ip}0/24.",
            "A regra de entrada do security group nao cobria as subnets do balanceador.",
            "Nenhum erro de aplicacao apareceu nos logs.",
        ),
        trigger_en="Client IP preservation exposed source addresses no ingress rule accepted.",
        trigger_pt="A preservacao do IP de origem expos enderecos que nenhuma regra de entrada aceitava.",
        mitigation_en="Allowed the balancer subnets on the required ports. Root cause addressed.",
        mitigation_pt="Liberamos as subnets do balanceador nas portas necessarias. Causa raiz tratada.",
        root_cause_open=False,
    ),
    Family(
        key="lb-app",
        title_en="Traffic imbalance plus an unguarded optional in the signing flow",
        title_pt="Desbalanceamento de trafego e optional sem guarda no fluxo de assinatura",
        signals_en=(
            "Node {node} carried twice the CPU of its peers with no traffic spike.",
            "Stickiness rehashed after the daily schedule restarted part of the fleet.",
            "Optional.get raised NoSuchElementException about {count} times.",
            "A ClassCastException followed in the same code path.",
            "The partner callback was never sent, so the document was invalid downstream.",
        ),
        signals_pt=(
            "O no {node} concentrou o dobro da CPU dos pares sem pico de trafego.",
            "A stickiness recalculou o hash depois que o schedule diario reiniciou parte da frota.",
            "Optional.get lancou NoSuchElementException cerca de {count} vezes.",
            "Um ClassCastException apareceu em seguida no mesmo caminho de codigo.",
            "O callback do parceiro nunca foi enviado, e o documento ficou invalido do lado dele.",
        ),
        trigger_en="A discriminator mismatch made the lookup return empty for a valid party.",
        trigger_pt="Divergencia de discriminator fez a busca retornar vazio para uma parte valida.",
        mitigation_en="DBA released stuck sessions while the team patched the lookup guard.",
        mitigation_pt="O DBA liberou sessoes travadas enquanto o time corrigia a guarda da busca.",
        root_cause_open=True,
    ),
    Family(
        key="slow-query",
        title_en="Slow queries after a statistics refresh",
        title_pt="Queries lentas depois de um refresh de estatisticas",
        signals_en=(
            "Query p99 went from {ms} ms to {ms2} ms right after the maintenance window.",
            "Slow query log filled with the same three statements.",
            "Database CPU reached {cpu}% without any pool saturation.",
            "A release had been deployed the evening before.",
        ),
        signals_pt=(
            "O p99 das queries saiu de {ms} ms para {ms2} ms logo apos a janela de manutencao.",
            "O log de query lenta encheu com os mesmos tres statements.",
            "CPU do banco chegou a {cpu}% sem qualquer saturacao de pool.",
            "Uma release havia sido publicada na noite anterior.",
        ),
        trigger_en="A stale execution plan survived the statistics refresh.",
        trigger_pt="Um plano de execucao velho sobreviveu ao refresh de estatisticas.",
        mitigation_en="Forced a plan invalidation. Root cause addressed with a scheduled refresh job.",
        mitigation_pt="Forcamos invalidacao do plano. Causa raiz tratada com job de refresh agendado.",
        root_cause_open=False,
    ),
)

# One-off incidents on purpose: a miner that finds a "pattern" in everything is broken.
ANECDOTES: tuple[tuple[str, str], ...] = (
    (
        "Disk filled on the log volume",
        "The log volume hit 100% disk full after debug logging was left enabled overnight. "
        "No space left on device appeared in the application log. Root cause addressed: "
        "log rotation restored and the debug flag reverted.",
    ),
    (
        "Backlog after a partner outage",
        "A partner endpoint was unavailable for two hours and the outbound queue depth grew "
        "steadily. Nothing was saturated locally. The backlog drained on its own once the "
        "partner recovered. Root cause addressed on the partner side.",
    ),
)

TEMPLATE = """---
id: {ident}
title: {title}
date: {date}
severity: {severity}
service: {service}
tags: [postmortem, synthetic]
---

# {title}

## Impact

{impact}

## Observed signals

{signals}

## Trigger

{trigger}

## Mitigation

{mitigation}

## Root cause

{root_cause}
"""


def _render(family: Family, index: int, rng: random.Random) -> tuple[str, str]:
    portuguese = rng.random() < _PT_RATIO
    values = {
        "cpu": rng.choice((84, 88, 92, 96, 98)),
        "mins": rng.choice((35, 45, 60, 90)),
        "pool": rng.choice((40, 60, 80)),
        "node": f"node-{rng.randint(1, 5)}",
        "hour": rng.randint(9, 19),
        "mb": rng.choice((18, 24, 31, 44)),
        "count": rng.choice((1200, 8400, 20100, 26800)),
        "threads": rng.choice((1800, 2600, 3100)),
        "days": rng.choice((1, 2, 3)),
        "ms": rng.choice((40, 60, 90)),
        "ms2": rng.choice((900, 1400, 2600)),
        "ip": "203.0.113.",
    }
    pool = family.signals_pt if portuguese else family.signals_en
    # Drop at most one signal so members of a family are similar but not identical.
    chosen = list(pool)
    if len(chosen) > _MIN_SIGNALS_TO_DROP and rng.random() < _DROP_CHANCE:
        chosen.pop(rng.randrange(len(chosen)))
    signals = "\n".join(f"- {line.format(**values)}" for line in chosen)

    month = (index % 6) + 1
    day = rng.randint(1, 27)
    root_cause = (
        (
            "Causa raiz estrutural nao tratada - a recorrencia deve continuar."
            if portuguese
            else "Root cause not addressed structurally - recurrence is expected."
        )
        if family.root_cause_open
        else ("Causa raiz tratada." if portuguese else "Root cause addressed.")
    )
    impact = (
        "Operacoes de clientes ficaram degradadas durante a janela do incidente."
        if portuguese
        else "Customer operations were degraded for the duration of the incident."
    )

    ident = f"{family.key}-{index:02d}"
    body = TEMPLATE.format(
        ident=ident,
        title=family.title_pt if portuguese else family.title_en,
        date=f"2026-{month:02d}-{day:02d}",
        severity=rng.choice(SEVERITIES),
        service=rng.choice(SERVICES),
        impact=impact,
        signals=signals,
        trigger=family.trigger_pt if portuguese else family.trigger_en,
        mitigation=family.mitigation_pt if portuguese else family.mitigation_en,
        root_cause=root_cause,
    )
    return f"postmortem-{ident}.md", body


def generate(out_dir: Path, count: int, seed: int) -> list[Path]:
    # Not cryptography: a fixed seed is the feature, so the README numbers stay true.
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("postmortem-*.md"):
        stale.unlink()

    written: list[Path] = []
    for index in range(count):
        family = FAMILIES[index % len(FAMILIES)]
        name, body = _render(family, index, rng)
        path = out_dir / name
        path.write_text(body, encoding="utf-8")
        written.append(path)

    for position, (title, prose) in enumerate(ANECDOTES, start=1):
        path = out_dir / f"postmortem-oneoff-{position:02d}.md"
        path.write_text(
            TEMPLATE.format(
                ident=f"oneoff-{position:02d}",
                title=title,
                date=f"2026-0{position + 2}-14",
                severity="P2",
                service=SERVICES[position % len(SERVICES)],
                impact="Limited impact, single occurrence.",
                signals=f"- {prose}",
                trigger="Single occurrence, no recurring trigger identified.",
                mitigation="Handled inline by the on-call engineer.",
                root_cause="Root cause addressed.",
            ),
            encoding="utf-8",
        )
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic postmortem corpus.")
    parser.add_argument("--out", type=Path, default=ROOT / "corpus")
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    written = generate(args.out, args.count, args.seed)
    print(f"wrote {len(written)} synthetic postmortems to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
