// Isolated loopback regression; never connects to the CARLA server.
#include "rpc/server.h"
#include "rpc/client.h"
#include <atomic>
#include <iostream>
#include <thread>
#include <vector>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

int main() {
    const unsigned short port = 28765;
    rpc::server server("127.0.0.1", port);
    server.bind("ping", [](){ return 42; });
    server.async_run(4);
    std::atomic<int> errors{0}, completed{0};
    std::vector<std::thread> workers;
    for (int worker = 0; worker < 4; ++worker) {
        workers.emplace_back([&](){
            for (int i = 0; i < 500; ++i) {
                try {
                    rpc::client client("127.0.0.1", port);
                    client.set_timeout(2000);
                    if (client.call("ping").as<int>() != 42) ++errors;
                    else ++completed;
                } catch (...) { ++errors; }
                const int fd = socket(AF_INET, SOCK_STREAM, 0);
                if (fd < 0) { ++errors; continue; }
                sockaddr_in address{};
                address.sin_family = AF_INET;
                address.sin_port = htons(port);
                inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
                if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) ++errors;
                // Alternate normal EOF and reset disconnects without RPC data.
                if (i % 2) { linger reset{1, 0}; setsockopt(fd, SOL_SOCKET, SO_LINGER, &reset, sizeof(reset)); }
                close(fd);
            }
        });
    }
    for (auto& worker : workers) worker.join();
    rpc::client final_client("127.0.0.1", port);
    final_client.set_timeout(2000);
    if (final_client.call("ping").as<int>() != 42) ++errors;
    server.stop();
    std::cout << "rpc_calls=" << completed << " errors=" << errors << std::endl;
    return errors == 0 && completed == 2000 ? 0 : 1;
}
