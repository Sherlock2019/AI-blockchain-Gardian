# Build context is the repository root: the deploy script reads ./data/agents.json.
FROM node:22-slim

WORKDIR /app/blockchain
COPY blockchain/package.json blockchain/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY blockchain/hardhat.config.js ./
COPY blockchain/contracts ./contracts
COPY blockchain/scripts ./scripts
COPY blockchain/tasks ./tasks
COPY data/agents.json /app/data/agents.json
RUN npx hardhat compile

ENV LEDGER_DEPLOYMENT_FILE=/deployments/localhost.json
EXPOSE 8545
CMD ["sh", "scripts/start-local.sh"]
