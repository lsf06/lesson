# The seeder embeds the ESP-DL model and two sample JPEGs taken straight from the
# repository (IDF's target_add_binary_data accepts absolute paths), so no 2.4 MB binary
# is duplicated inside this tool project. Embedded symbol names are derived from the
# file name only, therefore the sources are copied into this component's binary dir
# first - the same pattern used by extensions/03_live_catdog_assignment/main/CMakeLists.txt.
set(repo_root "${CMAKE_CURRENT_LIST_DIR}/../../../..")
set(model_src "${repo_root}/extensions/02_quantize_catdog_model/outputs/catdog_mobilenet_v2.espdl")
set(cat_src "${repo_root}/extensions/01_train_catdog_model/cats-dogs-data/valid/cat/cat.1001.jpg")
set(dog_src "${repo_root}/extensions/01_train_catdog_model/cats-dogs-data/valid/dog/dog.1001.jpg")

if(NOT EXISTS "${model_src}")
    message(FATAL_ERROR "Missing model file: ${model_src}")
endif()
if(NOT EXISTS "${cat_src}" OR NOT EXISTS "${dog_src}")
    message(FATAL_ERROR "Missing sample images: ${cat_src} / ${dog_src}")
endif()

configure_file("${model_src}" "${CMAKE_CURRENT_BINARY_DIR}/catdog_mobilenet_v2.espdl" COPYONLY)
configure_file("${cat_src}" "${CMAKE_CURRENT_BINARY_DIR}/sample_cat.jpg" COPYONLY)
configure_file("${dog_src}" "${CMAKE_CURRENT_BINARY_DIR}/sample_dog.jpg" COPYONLY)

idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    EMBED_FILES
        "${CMAKE_CURRENT_BINARY_DIR}/catdog_mobilenet_v2.espdl"
        "${CMAKE_CURRENT_BINARY_DIR}/sample_cat.jpg"
        "${CMAKE_CURRENT_BINARY_DIR}/sample_dog.jpg"
    REQUIRES fatfs sdmmc esp_driver_sdmmc mbedtls
)