FROM postgres:18

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-pip \
        python3-venv \
    && python3 -m venv /opt/patroni \
    && /opt/patroni/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/patroni/bin/pip install --no-cache-dir "patroni[etcd3]" psycopg2-binary \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY patroni-entrypoint.sh /usr/local/bin/patroni-entrypoint.sh

RUN chmod +x /usr/local/bin/patroni-entrypoint.sh \
    && mkdir -p /var/lib/postgresql/data/pgdata \
    && chown -R postgres:postgres /var/lib/postgresql /opt/patroni

USER postgres

ENTRYPOINT ["/usr/local/bin/patroni-entrypoint.sh"]
