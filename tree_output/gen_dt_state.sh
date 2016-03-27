for topo in egft jellyfish
do
    ./parse_tree_state.py -o tree_state.$topo.dt-nodfr.yaml B*/*$topo*dst.nodfr.*-t-*d.*
done
