cmake_minimum_required(VERSION 3.18)
project(wedge_native_backend LANGUAGES CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_native_engine app/core/native_engine/module.cpp)
target_compile_features(_native_engine PRIVATE cxx_std_17)

install(TARGETS _native_engine LIBRARY DESTINATION app/core/native_engine)
