for topo in "jellyfish" "egft"
do
    for model in line2 T alayer mlayer rand maxdag
    do
        echo Gathering $topo $model
        ./parse_tree_state.py --prefix $model */*.$topo.*$model* */*.$topo.*no*-t.*
    done
done
