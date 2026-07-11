#!/bin/bash
#SBATCH --job-name=numeric-planning
#SBATCH --partition=infai_2
#SBATCH --array=1-40
#SBATCH --time=00:35:00
#SBATCH --mem=4G
#SBATCH --output=logs/%A_%a.out
#SBATCH --error=logs/%A_%a.err

mkdir -p logs results

INSTANCES=(drone1 drone2 drone3 drone4 drone5 drone6 drone7 drone8 drone9 drone10
           drone11 drone12 drone13 drone14 drone15 drone16 drone17 drone18 drone19 drone20
           expedition1 expedition2 expedition3 expedition4 expedition5 expedition6 expedition7
           expedition8 expedition9 expedition10 expedition11 expedition12 expedition13 expedition14
           expedition15 expedition16 expedition17 expedition18 expedition19 expedition20)

INSTANCE=${INSTANCES[$SLURM_ARRAY_TASK_ID - 1]}

export DOWNWARD_BIN=/infai/erkek0000/downward/builds/release/bin/downward

echo "=== Array task $SLURM_ARRAY_TASK_ID: running $INSTANCE ==="
python3 run_pipeline.py "$INSTANCE"