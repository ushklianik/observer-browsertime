#!/bin/bash

args=$@
export reports=""
IFS=" " read -ra PARAMS <<< "$args"
for index in "${!PARAMS[@]}"
do
    if [[ ${PARAMS[index]} == "-tid" ]]; then
        test_id=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-r" ]]; then
        reports=$reports";"${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-sc" ]]; then
        script_name=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-l" ]]; then
        loops=${PARAMS[index + 1]}
    fi
    if [[ ${PARAMS[index]} == "-a" ]]; then
        aggregation=${PARAMS[index + 1]}
    fi
done

python3 /minio_tests_reader.py
echo "Scripts downloaded"
ls
echo "Start test"
/bin/bash /start.sh /$script_name --multi -n $loops --plugins.add analysisstorer $custom_cmd
echo "Test is done. Results processing..."
python3 /results_processing.py $test_id $script_name $loops $aggregation $reports
