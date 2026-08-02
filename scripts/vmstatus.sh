domain="win11"
virsh event --all --domain $domain | while read -r line; do
  echo "VM state changed: $line"
done
