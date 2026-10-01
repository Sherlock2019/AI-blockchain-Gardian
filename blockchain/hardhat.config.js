require("@nomicfoundation/hardhat-toolbox");
require("./tasks/agent");

/** Local development network only. No live network is configured on purpose. */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    localhost: { url: process.env.LEDGER_RPC_URL || "http://127.0.0.1:8545" },
  },
};
