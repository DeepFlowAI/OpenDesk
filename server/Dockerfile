ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=600 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Default to PyPI official index. CN users can switch to a faster mirror:
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ .
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG FASTTEXT_LANGUAGE_MODEL_URL=https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
ARG FASTTEXT_LANGUAGE_MODEL_SHA256=8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83

COPY requirements.txt .
RUN pip install --no-cache-dir --retries 10 \
    -i "${PIP_INDEX_URL}" \
    -r requirements.txt

RUN mkdir -p /app/models
RUN python -c "from urllib.request import urlretrieve; urlretrieve('${FASTTEXT_LANGUAGE_MODEL_URL}', '/app/models/lid.176.ftz')"
RUN echo "${FASTTEXT_LANGUAGE_MODEL_SHA256}  /app/models/lid.176.ftz" | sha256sum -c -

ENV FASTTEXT_LANGUAGE_MODEL_PATH=/app/models/lid.176.ftz

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
