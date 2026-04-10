FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/src \
    PYENV_ROOT=/opt/pyenv \
    PATH=/opt/pyenv/bin:/opt/pyenv/shims:$PATH

# Install tools used by the evaluation workflow and pyenv prerequisites.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    curl \
    git \
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libncursesw5-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    tk-dev \
    xz-utils \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pyenv for optional Python version management in interactive sessions.
RUN git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT" \
    && "$PYENV_ROOT/bin/pyenv" --version \
    && printf '\nexport PYENV_ROOT="/opt/pyenv"\nexport PATH="/opt/pyenv/bin:/opt/pyenv/shims:$PATH"\neval "$(pyenv init - bash)"\n' >> /root/.bashrc

WORKDIR /workspace

# Copy only the files needed to run the notebook and evaluation workflows.
COPY pyproject.toml README.md LICENSE evaluation.py run_small_eval.py example.ipynb ./
COPY middle ./middle
COPY src ./src

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install . \
    && python -m pip install jupyterlab ipykernel

# Default to an interactive shell so the same image can be used for ad-hoc
# evaluation runs, debugging, or manual notebook exploration.
CMD ["bash"]
