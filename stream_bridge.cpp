
/**
 * PeerCode Stream Bridge - High-performance C++ library for multimedia streaming
 * Created By Levi Enama
 * 
 * This library provides optimized functions for screen capture and multimedia processing
 * with Python bindings via ctypes. Currently implements simulation mode with optimized
 * memory buffers, ready to integrate with OS-specific capture APIs (GDI/DirectX on Windows,
 * X11/Wayland on Linux).
 */

#include <cstdint>
#include <cstring>
#include <chrono>
#include <thread>
#include <atomic>
#include <mutex>

// Version information
#define PEERCODE_STREAM_VERSION "0.1.0"

// Global state
static std::atomic<bool> g_initialized{false};
static std::atomic<bool> g_capturing{false};
static std::mutex g_frame_mutex;
static uint8_t* g_frame_buffer = nullptr;
static int g_frame_width = 1280;
static int g_frame_height = 720;
static int g_fps = 30;
static std::atomic<int64_t> g_frame_number{0};

// Frame format constants
#define PEERCODE_FRAME_BPP 4  // RGBA
#define PEERCODE_FRAME_SIZE(width, height) ((width) * (height) * PEERCODE_FRAME_BPP)

/**
 * Generate a test pattern frame for simulation
 */
static void generate_test_frame(uint8_t* buffer, int width, int height, int64_t frame_num) {
    int stride = width * PEERCODE_FRAME_BPP;
    
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int idx = y * stride + x * PEERCODE_FRAME_BPP;
            
            // Animated color pattern
            uint8_t r = static_cast<uint8_t>((x + frame_num * 2) % 256);
            uint8_t g = static_cast<uint8_t>((y + frame_num) % 256);
            uint8_t b = static_cast<uint8_t>((x + y + frame_num * 3) % 256);
            uint8_t a = 255;
            
            buffer[idx + 0] = r;
            buffer[idx + 1] = g;
            buffer[idx + 2] = b;
            buffer[idx + 3] = a;
        }
    }
    
    // Add PeerCode watermark
    const char* watermark = "PeerCode Stream";
    int text_x = 20;
    int text_y = height - 40;
    if (text_y > 0) {
        for (size_t i = 0; watermark[i]; ++i) {
            int char_x = text_x + i * 12;
            int char_y = text_y;
            if (char_x >= 0 && char_x + 10 < width && char_y >= 0 && char_y + 16 < height) {
                for (int dy = 0; dy < 16; ++dy) {
                    for (int dx = 0; dx < 10; ++dx) {
                        int idx = (char_y + dy) * stride + (char_x + dx) * PEERCODE_FRAME_BPP;
                        buffer[idx + 0] = 255;
                        buffer[idx + 1] = 255;
                        buffer[idx + 2] = 255;
                        buffer[idx + 3] = 255;
                    }
                }
            }
        }
    }
}

/**
 * Initialize the stream bridge
 * @return 0 on success, non-zero on error
 */
extern "C" int peercode_stream_init() {
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    
    if (g_initialized) {
        return 0;  // Already initialized
    }
    
    // Allocate frame buffer
    int buffer_size = PEERCODE_FRAME_SIZE(g_frame_width, g_frame_height);
    g_frame_buffer = new (std::nothrow) uint8_t[buffer_size];
    if (!g_frame_buffer) {
        return -1;  // Memory allocation failed
    }
    
    // Clear buffer
    std::memset(g_frame_buffer, 0, buffer_size);
    
    g_initialized = true;
    return 0;
}

/**
 * Start screen capture
 * @param fps Target frames per second
 * @param width Capture width (0 for default)
 * @param height Capture height (0 for default)
 * @return 0 on success, non-zero on error
 */
extern "C" int peercode_stream_start(int fps, int width, int height) {
    if (!g_initialized) {
        return -1;  // Not initialized
    }
    
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    
    // Update parameters
    g_fps = fps > 0 ? fps : 30;
    if (width > 0) g_frame_width = width;
    if (height > 0) g_frame_height = height;
    
    // Reallocate buffer if size changed
    int new_size = PEERCODE_FRAME_SIZE(g_frame_width, g_frame_height);
    int old_size = PEERCODE_FRAME_SIZE(1280, 720);  // Default
    if (g_frame_buffer) {
        delete[] g_frame_buffer;
    }
    g_frame_buffer = new (std::nothrow) uint8_t[new_size];
    if (!g_frame_buffer) {
        return -2;  // Memory allocation failed
    }
    std::memset(g_frame_buffer, 0, new_size);
    
    g_capturing = true;
    g_frame_number = 0;
    
    return 0;
}

/**
 * Get the latest captured frame
 * @param buffer Output buffer for frame data
 * @param buffer_size Size of the output buffer
 * @param out_size Output: actual size of frame data
 * @return 0 on success, non-zero on error
 */
extern "C" int peercode_stream_get_frame(uint8_t* buffer, int buffer_size, int* out_size) {
    if (!g_initialized || !buffer || !out_size) {
        return -1;
    }
    
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    
    int required_size = PEERCODE_FRAME_SIZE(g_frame_width, g_frame_height);
    if (buffer_size < required_size) {
        *out_size = required_size;
        return -2;  // Buffer too small
    }
    
    if (g_capturing) {
        // Generate next frame (simulation mode)
        generate_test_frame(g_frame_buffer, g_frame_width, g_frame_height, g_frame_number.load());
        g_frame_number++;
    }
    
    // Copy to output
    std::memcpy(buffer, g_frame_buffer, required_size);
    *out_size = required_size;
    
    return 0;
}

/**
 * Stop screen capture
 * @return 0 on success, non-zero on error
 */
extern "C" int peercode_stream_stop() {
    if (!g_initialized) {
        return -1;
    }
    
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    g_capturing = false;
    
    return 0;
}

/**
 * Shutdown the stream bridge and free resources
 * @return 0 on success, non-zero on error
 */
extern "C" int peercode_stream_shutdown() {
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    
    if (g_frame_buffer) {
        delete[] g_frame_buffer;
        g_frame_buffer = nullptr;
    }
    
    g_initialized = false;
    g_capturing = false;
    
    return 0;
}

/**
 * Get the stream bridge version
 * @return Version string
 */
extern "C" const char* peercode_stream_version() {
    return PEERCODE_STREAM_VERSION;
}

/**
 * Get current capture width
 * @return Current width
 */
extern "C" int peercode_stream_get_width() {
    return g_frame_width;
}

/**
 * Get current capture height
 * @return Current height
 */
extern "C" int peercode_stream_get_height() {
    return g_frame_height;
}

/**
 * Get current frame number
 * @return Current frame number
 */
extern "C" int64_t peercode_stream_get_frame_number() {
    return g_frame_number.load();
}

