#!/bin/bash

path="../hieradata/nodes/"

train_number=000
external_id_counter_101_140=000
external_id_counter_151_160=000
external_id_counter_201_240=000

# Create files for Train numbers 1 to 240
for ((i = 1; i <= 240; i++)); do
    # Skip train numbers 141 to 150 and 161 to 200
    if ((i >= 141 && i <= 150)) || ((i >= 161 && i <= 200)); then
        continue
    fi

    train_number=$(printf "%03d" $i)
    external_id="T4734${train_number}"
    if ((i <= 10)); then
        ip_address="213.208.157.7"
    elif ((i <= 21)); then
        ip_address="213.208.157.9"
    elif ((i <= 32)); then
        ip_address="213.208.157.77"
    elif ((i <= 42)); then
        ip_address="213.208.157.79"
    elif ((i >= 101 && i <= 140)); then # 6 Coach (NV)
        external_id_counter_101_140=$((external_id_counter_101_140+1))
        external_id=$(printf "%03d" $external_id_counter_101_140)
        external_id="T4736${external_id}"
    elif ((i >= 151 && i <= 160)); then # 5 Coach (NV)
        external_id_counter_151_160=$((external_id_counter_151_160+1))
        external_id=$(printf "%03d" $external_id_counter_151_160)
        external_id="T4735${external_id}"
    elif ((i >= 201 && i <= 240)); then # 6 Coach (FV)
        external_id_counter_201_240=$((external_id_counter_201_240+1))
        external_id=$(printf "%03d" $external_id_counter_201_240)
        external_id="T4706${external_id}"
    else
        ip_address="other_ip_address" # You can replace "other_ip_address" with the desired IP for the remaining trains
    fi

    filename="${path}box1-t${i}.dostoneu.21net.com.yaml"
    touch "$filename"
    echo "---" >> "$filename"
    echo "mar3_frontend::tunnel_remote_host: \"$ip_address\"" >> "$filename"
    echo "" >> "$filename" # Adding a new line
    echo "train_identification_api::external_id: \"$external_id\"" >> "$filename"
    echo "File $filename created with content."
done

# Create file for Nomad Bench (Train number 250)
external_id="NomadBench"
ip_address="213.208.157.79"
filename="${path}box1-t250.dostoneu.21net.com.yaml"
touch "$filename"
echo "---" >> "$filename"
echo "mar3_frontend::tunnel_remote_host: \"$ip_address\"" >> "$filename"
echo "" >> "$filename" # Adding a new line
echo "train_identification_api::external_id: \"$external_id\"" >> "$filename"
echo "File $filename created with content."

# Create file for Stadler Bench (Train number 245)
external_id="StadlerBench"
ip_address="213.208.157.79"
filename="${path}box1-t245.dostoneu.21net.com.yaml"
touch "$filename"
echo "---" >> "$filename"
echo "mar3_frontend::tunnel_remote_host: \"$ip_address\"" >> "$filename"
echo "" >> "$filename" # Adding a new line
echo "train_identification_api::external_id: \"$external_id\"" >> "$filename"
echo "File $filename created with content."
