
FROM node:22-alpine AS client-build

WORKDIR /client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
ARG VITE_BACKEND_URL=
ARG VITE_CLERK_PUBLISHABLE_KEY=
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN rm -rf /app/public
COPY --from=client-build /client/dist/ /app/public/

EXPOSE 7860

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "7860"]

