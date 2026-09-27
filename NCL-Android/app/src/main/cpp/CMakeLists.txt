cmake_minimum_required(VERSION 3.22.1)
project(nclgl CXX)

add_library(nclgl SHARED nclgl.cpp)

find_library(log-lib log)
find_library(android-lib android)

target_link_libraries(nclgl
        ${log-lib}
        ${android-lib})
