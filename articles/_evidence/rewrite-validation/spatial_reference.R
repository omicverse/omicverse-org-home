args <- commandArgs(trailingOnly=TRUE)
if (length(args) < 1) stop('Supply the workspace root as the first argument')
workspace <- normalizePath(args[[1]], winslash='/')
root <- workspace
input <- file.path(root,'outputs/rewrite-validation/spatial')
out <- file.path(root,'outputs/rewrite-validation/report-v2/spatial')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
suppressPackageStartupMessages({library(Matrix);library(Seurat);library(dplyr);library(SPATA2)})
source(file.path(root,'repos/SPLIT/R/method_agnostic_purification.R'))
source(file.path(root,'repos/SPLIT/R/neighborhood_analysis.R'))
source(file.path(root,'repos/SPLIT/R/balanced_dataset.R'))
source(file.path(root,'repos/SPLIT/R/residual_counts_reassignment.R'))
readm <- function(name) as.matrix(read.csv(file.path(input,name),row.names=1,check.names=FALSE))
x <- readm('split_counts.csv');w <- readm('split_weights.csv');ref <- readm('split_reference.csv')
obs <- read.csv(file.path(input,'split_obs.csv'),row.names=1,check.names=FALSE)
nn <- as.matrix(read.csv(file.path(input,'split_neighbors.csv'),header=FALSE))
primary <- setNames(obs$first_type,rownames(obs))
p <- rctd_free_purify(x,w,ref,primary)
# Build the R neighborhood object from shared graph inputs, not Python scores.
network <- list(cell_id=colnames(x),nn_idx=nn)
obs$second_type[is.na(obs$second_type) | obs$second_type == ''] <- NA_character_
obs$spot_class <- 'singlet'
obs$spot_class[seq(20,nrow(obs),40)] <- 'reject'
obs$spot_class[seq(10,nrow(obs),40)] <- 'doublet_uncertain'
for (key in c('first_type','second_type','weight_first_type','weight_second_type','spot_class'))
  network[[key]] <- matrix(obs[[key]][as.vector(nn)],nrow=nrow(nn))
network <- add_neighborhood_weight_composition(network)
network <- add_cell_types_neighborhood_weights(network)
network <- add_infiltration_metrics_to_neighborhood(network)
obs$neighborhood_weights_second_type <- network$neighborhood_weights_second_type
# Controlled swapping metadata, explicitly not inferred biological labels.
obs$first_type_neighborhood_agreement <- TRUE
obs$first_type_neighborhood_agreement[seq(1,nrow(obs),7)] <- FALSE
obs$first_type_class_neighborhood_agreement <- obs$first_type_neighborhood_agreement
obs$second_type_class <- obs$second_type
obs$first_type_class_neighborhood <- obs$second_type
raw <- CreateSeuratObject(x,assay='RNA',meta.data=obs)
pur <- CreateSeuratObject(p$purified_counts,assay='RNA',meta.data=p$cell_meta)
write.csv(obs,file.path(out,'split_control_metadata.csv'))
for (threshold in c(0.05,0.15,0.3,0.5)) for (swap in c(FALSE,TRUE)) {
  b <- balance_raw_and_purified_data_by_score(raw,pur,threshold=threshold,DO_swap_lables=swap,default_assay='RNA')
  bmat <- as.matrix(GetAssayData(b,layer='counts'))
  tag <- paste0('t',threshold,'_swap',as.integer(swap))
  write.csv(bmat,file.path(out,paste0('balanced_',tag,'.csv')))
  write.csv(b@meta.data,file.path(out,paste0('metadata_',tag,'.csv')))
}
coords <- read.csv(file.path(input,'spata_coords.csv'))
# Native SPATA2 SpatialData method, not a substitute dbscan-only call.
coords <- data.frame(barcodes=paste0('spot',seq_len(nrow(coords))),x_orig=coords$x,y_orig=coords$y)
placeholder <- Matrix(matrix(1,2,nrow(coords)),sparse=TRUE)
rownames(placeholder) <- c('placeholder1','placeholder2');colnames(placeholder) <- coords$barcodes
sp <- initiateSpataObject(sample_name='DLPFC151673',count_mtr=placeholder,modality='gene',coords_df=coords,spatial_method='VisiumSmall',verbose=FALSE)
sp <- identifyTissueOutline(sp,method='obs',eps=7.707226277274469,minPts=4,concavity=2,verbose=FALSE)
write.csv(getCoordsDf(sp,as_is=TRUE),file.path(out,'spata_native_coords.csv'),row.names=FALSE)
write.csv(getTissueOutlineDf(sp),file.path(out,'spata_native_outline.csv'),row.names=FALSE)
write.csv(getMetaDf(sp),file.path(out,'spata_native_labels.csv'),row.names=FALSE)
saveRDS(sp,file.path(out,'spata_native_spatialdata.rds'))
writeLines(capture.output(sessionInfo()),file.path(out,'sessionInfo.txt'))
