FROM carla-safety-base:26.04
# Archives are explicitly selected dependency payloads, never a host root/home backup.
# Keep original internal prefixes for Conda and precompiled UE libraries.
ADD engine.tar carla.tar e2e.tar ros.tar /
ADD frontend-deps.tar /opt/csa/frontend/
COPY node /opt/csa/bin/node
COPY manifest/ /opt/csa/manifest/
COPY entrypoint.sh /opt/csa/entrypoint.sh
RUN chmod 755 /opt/csa/entrypoint.sh /opt/csa/bin/node && \
    mkdir -p /workspace/tools/livery-designer/node_modules /workspace/.runtime /home/researcher/.cache && \
    chown -R 1000:1000 /home/researcher /workspace
ENV CARLA_ROOT=/home/moresweet/carla UE4_ROOT=/home/moresweet/UnrealEngine_4.26 \
    CSA_BUILD_MANIFEST=/opt/csa/manifest \
    E2E_ROOT=/home/moresweet/Data/e2e \
    UNIAD_PYTHON=/home/moresweet/Data/e2e/miniconda3/envs/uniad-cu128/bin/python \
    CARLA_PYTHONPATH=/home/moresweet/carla/.venv/lib/python3.14/site-packages \
    PATH=/opt/csa/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /workspace
USER researcher
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/opt/csa/entrypoint.sh"]
CMD ["studio"]
